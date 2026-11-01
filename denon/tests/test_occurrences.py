"""La prochaine occurrence d'une alarme et la règle de rattrapage : des
fonctions pures (fuseau, heure, jours, maintenant), sans base ni horloge."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from denon.backend.alarmes import prochaine_occurrence, situer
from denon.backend.ordonnanceur import echeance_de_test

PARIS = ZoneInfo("Europe/Paris")
UTC = timezone.utc
LUNDI, MARDI, MERCREDI, JEUDI, VENDREDI, SAMEDI, DIMANCHE = (1 << i for i in range(7))
SEMAINE = LUNDI | MARDI | MERCREDI | JEUDI | VENDREDI


def paris(texte: str) -> datetime:
    return datetime.fromisoformat(texte).replace(tzinfo=PARIS)


def prochaine(heure: str, jours: int, apres: datetime, fz=PARIS) -> str:
    return prochaine_occurrence(fz, time.fromisoformat(heure), jours, apres).astimezone(fz).isoformat()


def test_les_jours_de_la_semaine_sautent_le_week_end():
    # Vendredi 6 novembre 2026, 08:00 : l'alarme de 07:00 est passée.
    assert paris("2026-11-06T08:00").weekday() == 4
    assert prochaine("07:00", SEMAINE, paris("2026-11-06T08:00")) == "2026-11-09T07:00:00+01:00"
    assert prochaine("07:00", SEMAINE, paris("2026-11-06T06:59")) == "2026-11-06T07:00:00+01:00"
    assert prochaine("09:30", SAMEDI | DIMANCHE, paris("2026-11-06T08:00")) == "2026-11-07T09:30:00+01:00"
    # Strictement après : l'occurrence même ne compte pas.
    assert prochaine("07:00", SEMAINE, paris("2026-11-06T07:00")) == "2026-11-09T07:00:00+01:00"


def test_une_seule_fois_prend_la_prochaine_heure():
    assert prochaine("07:00", 0, paris("2026-11-06T06:00")) == "2026-11-06T07:00:00+01:00"
    assert prochaine("07:00", 0, paris("2026-11-06T08:00")) == "2026-11-07T07:00:00+01:00"


def test_les_secondes_comptent():
    assert prochaine("07:42:15", 0, paris("2026-11-06T07:42:14.900")) == "2026-11-06T07:42:15+01:00"


def test_passage_a_l_heure_d_ete_a_paris():
    # Dimanche 28 mars 2027 : à 02:00, on passe à 03:00 (+02:00).
    veille, jour = paris("2027-03-27T12:00"), paris("2027-03-28T00:00")
    assert prochaine("07:00", 0, veille) == "2027-03-28T07:00:00+02:00"
    assert prochaine("07:00", 0, paris("2027-03-27T00:00")) == "2027-03-27T07:00:00+01:00"
    # 02:30 n'existe pas ce jour-là : l'alarme part une heure plus tard,
    # à 03:30 heure d'été (01:30 UTC), une seule fois.
    occ = prochaine_occurrence(PARIS, time(2, 30), 0, jour)
    assert occ == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)
    assert occ.astimezone(PARIS).isoformat() == "2027-03-28T03:30:00+02:00"
    assert prochaine("02:30", 0, occ) == "2027-03-29T02:30:00+02:00"


def test_passage_a_l_heure_d_hiver_a_paris():
    # Dimanche 31 octobre 2027 : à 03:00, on revient à 02:00 (+01:00) ;
    # 02:30 existe deux fois. L'alarme ne part qu'à la première.
    jour = paris("2027-10-31T00:00")
    premiere = prochaine_occurrence(PARIS, time(2, 30), DIMANCHE, jour)
    assert premiere == datetime(2027, 10, 31, 0, 30, tzinfo=UTC)
    apres = prochaine_occurrence(PARIS, time(2, 30), DIMANCHE, premiere)
    assert apres.astimezone(PARIS).isoformat() == "2027-11-07T02:30:00+01:00"
    # La seconde 02:30 (01:30 UTC) n'est jamais une occurrence.
    assert prochaine_occurrence(PARIS, time(2, 30), 0, premiere).astimezone(PARIS).isoformat() == "2027-11-01T02:30:00+01:00"
    # Une heure ordinaire change de décalage, pas d'heure locale.
    assert prochaine("07:00", 0, jour) == "2027-10-31T07:00:00+01:00"
    assert prochaine("07:00", 0, paris("2027-10-30T00:00")) == "2027-10-30T07:00:00+02:00"


def test_un_autre_fuseau_que_paris():
    ny, tokyo = ZoneInfo("America/New_York"), ZoneInfo("Asia/Tokyo")
    # New York revient à l'heure d'hiver le 1er novembre 2026.
    samedi = datetime(2026, 10, 31, 0, 0, tzinfo=ny)
    assert prochaine_occurrence(ny, time(7), 0, samedi) == datetime(2026, 10, 31, 11, 0, tzinfo=UTC)
    dimanche = prochaine_occurrence(ny, time(7), 0, datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    assert dimanche == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    # Le même instant n'est pas le même jour partout : lundi 06:00 à Paris,
    # lundi 14:00 à Tokyo. Une alarme du lundi 07:00 à Tokyo est passée.
    instant = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)
    assert prochaine("07:00", LUNDI, instant, tokyo) == "2026-11-16T07:00:00+09:00"
    assert prochaine("07:00", LUNDI, instant) == "2026-11-09T07:00:00+01:00"


@pytest.mark.parametrize(
    ("maintenant", "attendu"),
    [
        ("2026-11-06T06:59:59", ("attendre", "2026-11-06T07:00:00+01:00")),
        ("2026-11-06T07:00:00", ("partir", "2026-11-06T07:00:00+01:00")),
        ("2026-11-06T07:05:00", ("partir", "2026-11-06T07:00:00+01:00")),
        ("2026-11-06T07:10:00", ("partir", "2026-11-06T07:00:00+01:00")),
        ("2026-11-06T07:10:01", ("manquee", "2026-11-06T07:00:00+01:00")),
    ],
)
def test_rattrapage_jusqu_a_dix_minutes(maintenant, attendu):
    etat, occ = situer(PARIS, time(7), SEMAINE, paris("2026-11-05T07:00"), paris(maintenant))
    assert (etat, occ.astimezone(PARIS).isoformat()) == attendu


def test_apres_plusieurs_jours_d_arret_seule_la_derniere_compte():
    # Arrêté du mardi au vendredi 07:05 : celle du vendredi part encore.
    base = paris("2026-11-03T07:00")
    etat, occ = situer(PARIS, time(7), SEMAINE, base, paris("2026-11-06T07:05"))
    assert (etat, occ) == ("partir", paris("2026-11-06T07:00").astimezone(UTC))
    etat, occ = situer(PARIS, time(7), SEMAINE, base, paris("2026-11-06T09:00"))
    assert (etat, occ) == ("manquee", paris("2026-11-06T07:00").astimezone(UTC))
    # Arrêtée des mois : rien à dérouler, on juge la dernière.
    etat, _ = situer(PARIS, time(7), SEMAINE, paris("2025-01-01T00:00"), paris("2026-11-06T07:01"))
    assert etat == "partir"


def test_une_alarme_armee_apres_son_heure_attend_le_lendemain():
    # Créée à 07:05 pour 07:00 : pas de rattrapage, ce n'est pas un retard.
    etat, occ = situer(PARIS, time(7), 0, paris("2026-11-06T07:05"), paris("2026-11-06T07:06"))
    assert (etat, occ.astimezone(PARIS).isoformat()) == ("attendre", "2026-11-07T07:00:00+01:00")


def test_une_alarme_unique_n_a_qu_une_occurrence():
    etat, occ = situer(PARIS, time(7), 0, paris("2026-11-01T12:00"), paris("2026-11-06T07:05"))
    assert (etat, occ) == ("manquee", paris("2026-11-02T07:00").astimezone(UTC))


def test_l_echeance_de_test_arrondit_a_la_seconde_suivante():
    t = datetime(2026, 11, 6, 6, 42, 10, 300000, tzinfo=UTC)
    assert echeance_de_test(t, 5) == datetime(2026, 11, 6, 6, 42, 16, tzinfo=UTC)
    assert echeance_de_test(t.replace(microsecond=0), 10) == t.replace(microsecond=0) + timedelta(seconds=10)
