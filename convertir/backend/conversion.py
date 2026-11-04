"""Ce que fait la conversion, sans base ni tampon : sonder, décider, encoder,
taguer, contrôler (#950).

Pourquoi un module sans état : l'aperçu (la carte, l'outil de la page
qualité) et l'application lisent **la même** décision (`decider`) — ce que
l'écran annonce est ce que le geste fera. Le contrôle final relit le fichier
écrit : un MP3 tronqué, raccourci ou sans ses tags n'est jamais posé.

Les sous-processus ont un délai et sont tués à l'annulation ; tout ce qui
lit ou écrit des tags (mutagen, synchrone) tourne hors de la boucle
d'événements — un fichier tordu ne fige jamais le serveur.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

# Les débits d'un MP3 MPEG-1 couche III : la cible est le premier palier
# **au moins égal** à la source. Jamais moins (on perdrait encore), jamais
# un palier « pour faire bien » au-dessus : réencoder ne rend rien de ce que
# le WMA a déjà jeté, un 320 depuis un 128 ne fait que grossir le fichier.
PALIERS = (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)

# Les codecs WMA avec perte que ffmpeg décode. Le WMA Lossless est écarté :
# le convertir en MP3 jetterait une copie sans perte (hors v1, vers FLAC).
CODECS_AVEC_PERTE = frozenset({"wmav1", "wmav2", "wmapro", "wmavoice"})
CODEC_SANS_PERTE = "wmalossless"

# Écart de durée toléré entre la source (lue par ffprobe) et le MP3. Un
# fichier sain s'en écarte de quelques centièmes ; une source abîmée que le
# décodeur saute en silence en perd davantage (mesuré : 0,2 s pour 0,5 %
# d'octets écrasés sur 30 s).
TOLERANCE_DUREE = 0.15

DELAI_SONDE = 30  # s
_sondes = asyncio.Semaphore(4)  # l'aperçu d'un album de 40 pistes ne lance pas 40 ffprobe d'un coup


def ffmpeg_disponible() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def palier(debit_kbps: int | None) -> int:
    """Le débit cible : le premier palier ≥ la source, 320 au plus. Source
    inconnue → 192, le débit le plus courant des WMA de la bibliothèque."""
    if not debit_kbps or debit_kbps <= 0:
        return 192
    return next((p for p in PALIERS if p >= debit_kbps), PALIERS[-1])


class EchecConversion(ValueError):
    """Un fichier que la conversion n'a pas su produire proprement : un refus
    attendu (`ValueError`), motivé, l'opération finit `failed` (#843)."""

    def __init__(self, motif: str, detail: str = ""):
        self.motif = motif
        super().__init__(f"{motif} : {detail}" if detail else motif)


async def _executer(*args: str, delai: float) -> tuple[int, bytes, bytes]:
    """Lance une commande ; au-delà de `delai` secondes, ou si la tâche est
    annulée, le processus est tué — il ne survit jamais au geste."""
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        sortie, erreur = await asyncio.wait_for(proc.communicate(), delai)
    except BaseException as e:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        if isinstance(e, asyncio.TimeoutError):
            raise EchecConversion("delai", f"{args[0]} n'a pas fini en {delai:.0f} s") from None
        raise
    return proc.returncode, sortie, erreur


async def sonder(fichier: Path) -> dict | None:
    """Codec, débit (kbps) et durée du premier flux audio, ou `None` si
    ffprobe ne lit pas le fichier."""
    async with _sondes:
        try:
            code, sortie, _ = await _executer(
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,bit_rate:format=duration,bit_rate",
                "-of", "json", str(fichier), delai=DELAI_SONDE,
            )
        except EchecConversion:
            return None
    if code != 0:
        return None
    try:
        donnees = json.loads(sortie or b"{}")
    except ValueError:
        return None
    flux = (donnees.get("streams") or [{}])[0]
    fmt = donnees.get("format") or {}
    if not flux.get("codec_name"):
        return None

    def kbps(v):
        try:
            return round(int(v) / 1000) or None
        except (TypeError, ValueError):
            return None

    try:
        duree = float(fmt.get("duration"))
    except (TypeError, ValueError):
        duree = None
    return {"codec": flux["codec_name"], "debit": kbps(flux.get("bit_rate")) or kbps(fmt.get("bit_rate")),
            "duree": duree}


def nom_valide(nom: str) -> bool:
    """La règle du cœur (`pistes_remplacement.nom_valide`), jugée dès
    l'aperçu : un nom refusé ne doit pas coûter l'encodage d'un album."""
    return (bool(nom) and nom == nom.strip() and "/" not in nom and "\\" not in nom
            and nom not in (".", "..") and not nom.startswith("."))


def nom_cible(source: str) -> str:
    """Le nom du MP3 : celui du WMA, débarrassé des espaces et points de
    bord qu'un nom de fichier visible ne peut pas porter."""
    tige = PurePosixPath(source).stem.strip().lstrip(".").strip()
    return f"{tige}.mp3" if tige else ""


@dataclass
class Piste:
    """Une ligne de l'aperçu : ce que deviendra (ou non) une piste."""

    track_id: int
    source: str  # chemin relatif à /music
    format: str
    codec: str | None
    debit_source: int | None
    debit_cible: int | None
    nom_cible: str | None
    convertible: bool
    motif: str | None = None  # pourquoi elle ne l'est pas
    duree: float | None = None
    ecartes: list[str] = field(default_factory=list)  # tags qui ne seront pas recopiés

    def vue(self) -> dict:
        return asdict(self)


def decider(track: dict, sonde: dict | None, existe, *, ffmpeg: bool = True) -> Piste:
    """La décision pour une piste WMA. `track` : une ligne de `tracks`
    (`id`, `relative_path`, `format`, `bitrate_kbps`) ; `existe(chemin)` dit
    si un chemin relatif est déjà pris sur le disque."""
    base = dict(track_id=track["id"], source=track["relative_path"], format=track["format"])
    if not ffmpeg:
        return Piste(**base, codec=None, debit_source=track.get("bitrate_kbps"), debit_cible=None,
                     nom_cible=None, convertible=False, motif="ffmpeg_absent")
    if sonde is None:
        return Piste(**base, codec=None, debit_source=track.get("bitrate_kbps"), debit_cible=None,
                     nom_cible=None, convertible=False, motif="illisible")
    codec = sonde["codec"]
    debit = track.get("bitrate_kbps") or sonde.get("debit")
    commun = dict(codec=codec, debit_source=debit, duree=sonde.get("duree"))
    if codec == CODEC_SANS_PERTE:
        return Piste(**base, **commun, debit_cible=None, nom_cible=None, convertible=False, motif="sans_perte")
    if codec not in CODECS_AVEC_PERTE:
        return Piste(**base, **commun, debit_cible=None, nom_cible=None, convertible=False, motif="codec_inconnu")
    nom = nom_cible(track["relative_path"])
    if not nom_valide(nom):
        return Piste(**base, **commun, debit_cible=palier(debit), nom_cible=None, convertible=False,
                     motif="nom_invalide")
    dest = str(PurePosixPath(track["relative_path"]).parent / nom)
    if existe(dest):
        return Piste(**base, **commun, debit_cible=palier(debit), nom_cible=nom, convertible=False,
                     motif="place_prise")
    return Piste(**base, **commun, debit_cible=palier(debit), nom_cible=nom, convertible=True)


# ── Tags : ASF → ID3v2.4 ─────────────────────────────────────────────────
#
# Les mêmes noms que lit le scanner du cœur (#504), recopiés dans les cadres
# ID3 qu'il relit pour un MP3 (et que Picard écrit). Ce qui ne se recopie pas
# fidèlement (une année illisible) est **écarté et annoncé**, jamais deviné :
# il reste dans l'original, à la corbeille.

TEXTE = {
    "Title": "TIT2",
    "Author": "TPE1",
    "WM/AlbumTitle": "TALB",
    "WM/AlbumArtist": "TPE2",
    "WM/PartOfSet": "TPOS",
    "WM/Genre": "TCON",
    "WM/Composer": "TCOM",
    "WM/Conductor": "TPE3",
    "WM/Publisher": "TPUB",
    "WM/ISRC": "TSRC",
    "WM/EncodedBy": "TENC",
    "Copyright": "TCOP",
    "WM/ArtistSortOrder": "TSOP",
    "WM/AlbumSortOrder": "TSOA",
    "WM/AlbumArtistSortOrder": "TSO2",
}
DATES = {"WM/Year": "TDRC", "WM/OriginalReleaseYear": "TDOR"}
TXXX = {
    "MusicBrainz/Artist Id": "MusicBrainz Artist Id",
    "MusicBrainz/Album Id": "MusicBrainz Album Id",
    "MusicBrainz/Album Artist Id": "MusicBrainz Album Artist Id",
    "MusicBrainz/Release Group Id": "MusicBrainz Release Group Id",
    "MusicBrainz/Release Track Id": "MusicBrainz Release Track Id",
    "MusicBrainz/Album Type": "MusicBrainz Album Type",
    "MusicBrainz/Album Status": "MusicBrainz Album Status",
    "MusicBrainz/Album Release Country": "MusicBrainz Album Release Country",
    "WM/Barcode": "BARCODE",
    "WM/CatalogNo": "CATALOGNUMBER",
    "WM/ARTISTS": "ARTISTS",
    "replaygain_track_gain": "REPLAYGAIN_TRACK_GAIN",
    "replaygain_track_peak": "REPLAYGAIN_TRACK_PEAK",
    "replaygain_album_gain": "REPLAYGAIN_ALBUM_GAIN",
    "replaygain_album_peak": "REPLAYGAIN_ALBUM_PEAK",
}
# L'enregistrement MusicBrainz vit dans un UFID (convention Picard).
UFID_MB = "MusicBrainz/Track Id"
# Une date ID3 : AAAA, AAAA-MM ou AAAA-MM-JJ (le reste d'un horodatage ISO est coupé).
_DATE = re.compile(r"^(\d{4})(-\d{2}(-\d{2})?)?(T.*)?$")
_GENRE_NUMERIQUE = re.compile(r"^\(?(\d{1,3})\)?(.*)$")


def _valeurs(attributs) -> list[str]:
    """Le texte d'un attribut ASF, quel que soit son type (texte, entier,
    booléen) ; les tableaux d'octets n'ont pas de texte."""
    sortie = []
    for a in attributs or []:
        v = getattr(a, "value", a)
        if isinstance(v, (bytes, bytearray)):
            continue
        texte = str(v).strip()
        if texte:
            sortie.append(texte)
    return sortie


def _piste(tags) -> str | None:
    """`WM/TrackNumber` (1-indexé) d'abord, sinon l'ancien `WM/Track`
    (0-indexé)."""
    for v in _valeurs(tags.get("WM/TrackNumber")):
        return v
    for v in _valeurs(tags.get("WM/Track")):
        try:
            return str(int(v) + 1)
        except ValueError:
            return None
    return None


def _date(texte: str) -> str | None:
    m = _DATE.match(texte)
    return texte[: len(texte) - len(m.group(4) or "")] if m else None


def _genre(texte: str) -> str:
    """Un genre ID3v1 numérique (« 13 », « (12)Other ») devient son libellé,
    comme le ferait mutagen à l'enregistrement — mais ici, avant le contrôle."""
    from mutagen._constants import GENRES

    m = _GENRE_NUMERIQUE.match(texte)
    if not m:
        return texte
    n, reste = int(m.group(1)), m.group(2).strip()
    if reste:
        return reste
    return GENRES[n] if n < len(GENRES) else texte


def lire_image_asf(brut: bytes) -> dict | None:
    """Décode un `WM/Picture` : type (1 octet), taille (4, LE), type MIME et
    description en UTF-16LE terminés par un nul, puis l'image. Toute forme
    inattendue rend `None` — jamais une boucle qui ne finit pas."""
    try:
        brut = bytes(brut)
        type_image = brut[0]
        (taille,) = struct.unpack_from("<I", brut, 1)
        pos = 5
        champs = []
        for _ in range(2):
            fin = pos
            while fin + 1 < len(brut) and brut[fin:fin + 2] != b"\x00\x00":
                fin += 2
            if fin + 1 >= len(brut):
                return None
            champs.append(brut[pos:fin].decode("utf-16-le"))
            pos = fin + 2
        donnees = brut[pos:pos + taille]
    except (IndexError, struct.error, UnicodeDecodeError, TypeError):
        return None
    if len(donnees) != taille or not donnees:
        return None
    return {"type": type_image, "mime": champs[0] or "image/jpeg", "desc": champs[1], "data": donnees}


def tags_id3(source: Path) -> tuple[list, list[str]]:
    """Les cadres ID3 à écrire, lus dans les tags ASF de la source, et ce qui
    ne sera pas recopié (lisible à l'aperçu)."""
    from mutagen.asf import ASF
    from mutagen.id3 import APIC, COMM, TRCK, USLT, Frames, UFID
    from mutagen.id3 import TXXX as CadreTXXX

    tags = ASF(str(source)).tags or {}
    cadres, ecartes = [], []
    for cle, nom in TEXTE.items():
        valeurs = _valeurs(tags.get(cle))
        if cle == "WM/Genre":
            valeurs = [_genre(v) for v in valeurs]
        if valeurs:
            cadres.append(Frames[nom](encoding=3, text=valeurs))
    for cle, nom in DATES.items():
        valeurs = _valeurs(tags.get(cle))
        lisibles = [d for d in (_date(v) for v in valeurs) if d]
        ecartes += [f"{cle} « {v} »" for v in valeurs if not _date(v)]
        if lisibles:
            cadres.append(Frames[nom](encoding=3, text=lisibles[:1]))
    numero = _piste(tags)
    if numero:
        cadres.append(TRCK(encoding=3, text=[numero]))
    for cle, desc in TXXX.items():
        valeurs = _valeurs(tags.get(cle))
        if valeurs:
            cadres.append(CadreTXXX(encoding=3, desc=desc, text=valeurs))
    for v in _valeurs(tags.get(UFID_MB))[:1]:
        cadres.append(UFID(owner="http://musicbrainz.org", data=v.encode()))
    for v in _valeurs(tags.get("Description"))[:1]:
        cadres.append(COMM(encoding=3, lang="XXX", desc="", text=[v]))
    for v in _valeurs(tags.get("WM/Lyrics"))[:1]:
        cadres.append(USLT(encoding=3, lang="XXX", desc="", text=v))
    images = []
    for a in tags.get("WM/Picture") or []:
        image = lire_image_asf(getattr(a, "value", b""))
        if image is None:
            ecartes.append("WM/Picture illisible")
        else:
            images.append(image)
    # Le recto d'abord : c'est la première image que lisent la plupart des lecteurs.
    images.sort(key=lambda i: i["type"] != 3)
    for n, image in enumerate(images):
        # La description distingue les cadres APIC : deux images sans
        # description s'écraseraient l'une l'autre.
        desc = image["desc"] or ("" if n == 0 else f"image {n + 1}")
        cadres.append(APIC(encoding=3, mime=image["mime"], type=image["type"], desc=desc, data=image["data"]))
    return cadres, ecartes


def _duree_entete(source: Path) -> float | None:
    from mutagen.asf import ASF

    try:
        return ASF(str(source)).info.length or None
    except Exception:  # noqa: BLE001 — sans en-tête lisible, on garde la durée sondée
        return None


def ecartes_de(source: Path) -> list[str]:
    """Ce que la conversion de `source` ne recopiera pas — pour l'aperçu."""
    try:
        return tags_id3(source)[1]
    except Exception as e:  # noqa: BLE001 — un fichier que mutagen ne lit pas
        return [f"tags illisibles ({type(e).__name__})"]


def _ecrire_et_attendre(mp3: Path, cadres: list) -> dict:
    """Écrit les cadres en ID3v2.4 et rend ce qu'on doit relire : les cadres
    **tels que mutagen les enregistre** (`update_to_v24`), pas tels qu'on les
    a construits."""
    from mutagen.id3 import ID3

    id3 = ID3()
    for c in cadres:
        id3.add(c)
    id3.update_to_v24()
    attendus = _empreinte_tags(id3.values())
    id3.save(str(mp3), v2_version=4)
    return attendus


def _empreinte_tags(cadres) -> dict:
    return {c.HashKey: str(getattr(c, "text", None) or getattr(c, "data", None)) for c in cadres}


def controler(mp3: Path, debit: int, duree_source: float | None, attendus: dict) -> None:
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3, HeaderNotFoundError

    try:
        info = MP3(str(mp3)).info
    except HeaderNotFoundError as e:
        raise EchecConversion("controle", f"MP3 illisible : {e}") from None
    if duree_source and abs(info.length - duree_source) > TOLERANCE_DUREE:
        raise EchecConversion("controle", f"durée {info.length:.2f} s au lieu de {duree_source:.2f} s "
                              "(source abîmée ?)")
    if round(info.bitrate / 1000) != debit:
        raise EchecConversion("controle", f"débit {round(info.bitrate / 1000)} kbps au lieu de {debit}")
    relus = _empreinte_tags(ID3(str(mp3)).values())
    manquants = sorted(k for k, v in attendus.items() if relus.get(k) != v)
    if manquants:
        raise EchecConversion("controle", f"tags non relus : {', '.join(manquants)}")


async def convertir(source: Path, cible: Path, debit: int, duree_source: float | None) -> list[str]:
    """Encode `source` en MP3 CBR `debit` kbps dans `cible`, recopie ses
    tags, puis relit le résultat : durée, débit, tags. Rend les tags écartés ;
    lève `EchecConversion`."""
    cadres, ecartes = await asyncio.to_thread(tags_id3, source)
    # La durée de référence est celle de l'en-tête ASF (lue par mutagen, comme
    # le scanner du cœur) : ffprobe estime parfois la sienne de travers sur un
    # WMA tagué (2,40 s annoncées pour 2 s réelles). Une source abîmée garde
    # son en-tête : c'est l'écart avec lui qui la trahit.
    duree_source = await asyncio.to_thread(_duree_entete, source) or duree_source
    delai = max(120.0, 2 * (duree_source or 0) + 60)
    code, _, erreur = await _executer(
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-map", "0:a:0", "-map_metadata", "-1", "-vn",
        "-c:a", "libmp3lame", "-b:a", f"{debit}k", "-write_xing", "1", str(cible),
        delai=delai,
    )
    if code != 0 or not cible.is_file():
        raise EchecConversion("encodage", erreur.decode(errors="replace").strip()[-300:] or f"ffmpeg a rendu {code}")
    attendus = await asyncio.to_thread(_ecrire_et_attendre, cible, cadres)
    await asyncio.to_thread(controler, cible, debit, duree_source, attendus)
    return ecartes
