"""Ce que fait la conversion, sans base ni tampon : sonder, décider, encoder,
taguer, contrôler (#950).

Pourquoi un module sans état : l'aperçu (la carte, l'outil de la page
qualité) et l'application lisent **la même** décision (`decider`) — ce que
l'écran annonce est ce que le geste fera. Le contrôle final relit le fichier
écrit : un MP3 tronqué ou sans ses tags n'est jamais posé dans `/music`.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import struct
from dataclasses import asdict, dataclass
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

# Écart de durée toléré entre la source et le MP3 (le décodeur et le
# remplissage de trame de LAME déplacent la fin de quelques dizaines de ms).
TOLERANCE_DUREE = 1.0


def ffmpeg_disponible() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def palier(debit_kbps: int | None) -> int:
    """Le débit cible : le premier palier ≥ la source, 320 au plus. Source
    inconnue → 192, le débit le plus courant des WMA de la bibliothèque."""
    if not debit_kbps or debit_kbps <= 0:
        return 192
    return next((p for p in PALIERS if p >= debit_kbps), PALIERS[-1])


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

    def vue(self) -> dict:
        return asdict(self)


async def _executer(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    sortie, erreur = await proc.communicate()
    return proc.returncode, sortie, erreur


async def sonder(fichier: Path) -> dict | None:
    """Codec, débit (kbps) et durée du premier flux audio, ou `None` si
    ffprobe ne lit pas le fichier."""
    code, sortie, _ = await _executer(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,bit_rate:format=duration,bit_rate",
        "-of", "json", str(fichier),
    )
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
    return {
        "codec": flux["codec_name"],
        "debit": kbps(flux.get("bit_rate")) or kbps(fmt.get("bit_rate")),
        "duree": duree,
    }


def nom_cible(source: str) -> str:
    return PurePosixPath(source).stem + ".mp3"


def decider(track: dict, sonde: dict | None, existe) -> Piste:
    """La décision pour une piste WMA. `track` : une ligne de `tracks`
    (`id`, `relative_path`, `format`, `bitrate_kbps`) ; `existe(chemin)` dit
    si un chemin relatif est déjà pris sur le disque."""
    base = dict(track_id=track["id"], source=track["relative_path"], format=track["format"])
    if sonde is None:
        return Piste(**base, codec=None, debit_source=track.get("bitrate_kbps"), debit_cible=None,
                     nom_cible=None, convertible=False, motif="illisible")
    codec = sonde["codec"]
    debit = track.get("bitrate_kbps") or sonde.get("debit")
    if codec == CODEC_SANS_PERTE:
        return Piste(**base, codec=codec, debit_source=debit, debit_cible=None, nom_cible=None,
                     convertible=False, motif="sans_perte")
    if codec not in CODECS_AVEC_PERTE:
        return Piste(**base, codec=codec, debit_source=debit, debit_cible=None, nom_cible=None,
                     convertible=False, motif="codec_inconnu")
    nom = nom_cible(track["relative_path"])
    dest = str(PurePosixPath(track["relative_path"]).parent / nom)
    if existe(dest):
        return Piste(**base, codec=codec, debit_source=debit, debit_cible=palier(debit), nom_cible=nom,
                     convertible=False, motif="place_prise")
    return Piste(**base, codec=codec, debit_source=debit, debit_cible=palier(debit), nom_cible=nom,
                 convertible=True)


# ── Tags : ASF → ID3v2.4 ─────────────────────────────────────────────────
#
# Les mêmes noms que lit le scanner du cœur (#504), recopiés dans les cadres
# ID3 qu'il relit pour un MP3 (et que Picard écrit). Ce qui n'a pas de cadre
# connu n'est pas inventé : il reste dans l'original, à la corbeille.

TEXTE = {
    "Title": "TIT2",
    "Author": "TPE1",
    "WM/AlbumTitle": "TALB",
    "WM/AlbumArtist": "TPE2",
    "WM/PartOfSet": "TPOS",
    "WM/Year": "TDRC",
    "WM/OriginalReleaseYear": "TDOR",
    "WM/Genre": "TCON",
    "WM/Composer": "TCOM",
    "WM/Conductor": "TPE3",
    "WM/Publisher": "TPUB",
    "WM/ISRC": "TSRC",
    "Copyright": "TCOP",
    "WM/ArtistSortOrder": "TSOP",
    "WM/AlbumSortOrder": "TSOA",
    "WM/AlbumArtistSortOrder": "TSO2",
}
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
}
# L'enregistrement MusicBrainz vit dans un UFID (convention Picard).
UFID_MB = "MusicBrainz/Track Id"


def _valeurs(attributs) -> list[str]:
    sortie = []
    for a in attributs or []:
        v = getattr(a, "value", a)
        if isinstance(v, bytes):
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


def lire_image_asf(brut: bytes) -> dict | None:
    """Décode un `WM/Picture` : type (1 octet), taille (4, LE), type MIME et
    description en UTF-16LE terminés par un nul, puis l'image."""
    try:
        type_image = brut[0]
        (taille,) = struct.unpack_from("<I", brut, 1)
        pos = 5
        champs = []
        for _ in range(2):
            fin = pos
            while brut[fin:fin + 2] != b"\x00\x00":
                fin += 2
            champs.append(brut[pos:fin].decode("utf-16-le"))
            pos = fin + 2
        donnees = brut[pos:pos + taille]
    except (IndexError, struct.error, UnicodeDecodeError):
        return None
    if len(donnees) != taille or not donnees:
        return None
    return {"type": type_image, "mime": champs[0] or "image/jpeg", "desc": champs[1], "data": donnees}


def tags_id3(source: Path) -> list:
    """Les cadres ID3 à écrire, lus dans les tags ASF de la source."""
    from mutagen.asf import ASF
    from mutagen.id3 import APIC, TRCK, TXXX as CadreTXXX, UFID, Frames

    tags = ASF(str(source)).tags or {}
    cadres = []
    for cle, nom in TEXTE.items():
        valeurs = _valeurs(tags.get(cle))
        if valeurs:
            cadres.append(Frames[nom](encoding=3, text=valeurs))
    numero = _piste(tags)
    if numero:
        cadres.append(TRCK(encoding=3, text=[numero]))
    for cle, desc in TXXX.items():
        valeurs = _valeurs(tags.get(cle))
        if valeurs:
            cadres.append(CadreTXXX(encoding=3, desc=desc, text=valeurs))
    for v in _valeurs(tags.get(UFID_MB))[:1]:
        cadres.append(UFID(owner="http://musicbrainz.org", data=v.encode()))
    for a in tags.get("WM/Picture") or []:
        image = lire_image_asf(getattr(a, "value", b""))
        if image:
            cadres.append(APIC(encoding=3, mime=image["mime"], type=image["type"], desc=image["desc"],
                               data=image["data"]))
            break
    return cadres


def ecrire_tags(mp3: Path, cadres: list) -> None:
    from mutagen.id3 import ID3

    id3 = ID3()
    for c in cadres:
        id3.add(c)
    id3.save(str(mp3), v2_version=4)


def _empreinte_tags(cadres: list) -> dict:
    return {c.HashKey: getattr(c, "text", None) or getattr(c, "data", None) for c in cadres}


class EchecConversion(ValueError):
    """Un fichier que la conversion n'a pas su produire proprement : un refus
    attendu (`ValueError`), motivé, l'opération finit `failed` (#843)."""

    def __init__(self, motif: str, detail: str = ""):
        self.motif = motif
        super().__init__(f"{motif} : {detail}" if detail else motif)


async def convertir(source: Path, cible: Path, debit: int, duree_source: float | None) -> None:
    """Encode `source` en MP3 CBR `debit` kbps dans `cible`, recopie ses
    tags, puis relit le résultat : durée, débit, tags. Lève `EchecConversion`."""
    cadres = tags_id3(source)
    code, _, erreur = await _executer(
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-map", "0:a:0", "-map_metadata", "-1", "-vn",
        "-c:a", "libmp3lame", "-b:a", f"{debit}k", "-write_xing", "1", str(cible),
    )
    if code != 0 or not cible.is_file():
        raise EchecConversion("encodage", erreur.decode(errors="replace").strip()[-300:] or f"ffmpeg a rendu {code}")
    ecrire_tags(cible, cadres)
    controler(cible, debit, duree_source, cadres)


def controler(mp3: Path, debit: int, duree_source: float | None, cadres: list) -> None:
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3, HeaderNotFoundError

    try:
        info = MP3(str(mp3)).info
    except HeaderNotFoundError as e:
        raise EchecConversion("controle", f"MP3 illisible : {e}") from None
    if duree_source and abs(info.length - duree_source) > TOLERANCE_DUREE:
        raise EchecConversion("controle", f"durée {info.length:.1f} s au lieu de {duree_source:.1f} s")
    if round(info.bitrate / 1000) != debit:
        raise EchecConversion("controle", f"débit {round(info.bitrate / 1000)} kbps au lieu de {debit}")
    relus = _empreinte_tags(ID3(str(mp3)).values())
    attendus = _empreinte_tags(cadres)
    manquants = sorted(k for k, v in attendus.items() if relus.get(k) != v)
    if manquants:
        raise EchecConversion("controle", f"tags non relus : {', '.join(manquants)}")
