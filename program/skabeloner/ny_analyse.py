"""Opretter en ny analysemappe med datamapper, config.yaml og koer_analyse.bat.

Functionality: startes af ny_analyse.bat i værktøjsmappen (filen her ligger i program\\skabeloner\\).
    Spørger om et navn og opretter <mappen ved siden af værktøjsmappen>\\trackpoint_analyser\\<navn>\\ med data\\A, data\\B, resultat,
    config.yaml (fra skabeloner\\config.yaml) og koer_analyse.bat (stien til værktøjet er sat ind).
Uses: kun Python standardbibliotek.
Dependencies: skabeloner\\config.yaml og skabeloner\\koer_analyse.bat ved siden af denne fil.
Debugging points: navnet må ikke indeholde \\ / : * ? " < > |, og værktøjets sti må ikke indeholde %
    (bat-filen kan ikke rumme det). Findes mappen, stopper scriptet
    uden at røre den. --rod vælger en anden placering end trackpoint_analyser ved siden af værktøjet.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKABELONER = Path(__file__).resolve().parent
VAERKTOEJ = SKABELONER.parent          # program\ (mappen med analyse_v2.2.py); sættes ind i koer_analyse.bat
PAKKE = VAERKTOEJ.parent               # værktøjsmappen; analyserne oprettes ved siden af den
ULOVLIGE = set('\\/:*?"<>|')

SAADAN = """Sådan laver du analysen
=======================

1. Læg HAFAS-eksporten i mapperne:  data\\A  (før)  og  data\\B  (efter).
   Hver mappe skal have Details.csv og List.csv. Vejledning: vejledning\\eksportvejledning_HAFAS.md i værktøjsmappen.
2. Åbn config.yaml (fx i Notesblok), og udfyld felterne med  <-- UDFYLD:
   perioder, strækningens to ender (p1, p2) og elementerne. Bump: radius_m = 30 passer til et almindeligt enkelt bump.
3. Dobbeltklik på koer_analyse.bat:
     0 = første gang: installér og test
     1 = stoppesteder pr. retning: stopnavne.txt foreslår start og slut for hver retning;
         kopiér dem ind i config.yaml (punkt 4). Står der OBS nederst, så byt p1 og p2 først.
     2 = prøvekørsel: tjek resultat\\proeve\\kvalitet.md
     3 = fuld analyse og rapport
4. Se resultat\\rapport.html. Køretid pr. tur: resultat\\turtabel.csv (Excel/Power BI); pr. time: resultat\\overblik.md.
   Skriv titlen (fundet i én sætning) og teksterne i config.yaml, og vælg 4 for at bygge rapporten igen.
5. Tilføj dine fund i nationale_analysekonklusioner.md i værktøjsmappen, og del dem via repoet på GitHub (pull request eller issue).

Kun én periode: sæt PERIODER=A øverst i koer_analyse.bat.
Forbehold og hvordan tallene er regnet: vejledning\\metode_og_rapportering.md i værktøjsmappen.
Værktøjet: {vaerktoej}
"""


def main():
    ap = argparse.ArgumentParser(description="Opretter en ny analysemappe.")
    ap.add_argument("--navn", help="analysens navn, fx 'Kvaglundvej Esbjerg' (ellers spørges der)")
    ap.add_argument("--rod", help="mappe, analysen oprettes i (standard: trackpoint_analyser ved siden af værktøjet)")
    ap.add_argument("--ingen-explorer", action="store_true", help="åbn ikke mappen bagefter")
    a = ap.parse_args()

    if "%" in str(VAERKTOEJ):
        sys.exit(f"Værktøjsmappens sti indeholder %, som koer_analyse.bat ikke kan rumme. Flyt værktøjsmappen: {PAKKE}")
    navn = (a.navn or input("Navn på analysen (fx Kvaglundvej Esbjerg): ")).strip()
    if not navn or ULOVLIGE & set(navn):
        sys.exit('Navnet må ikke være tomt eller indeholde \\ / : * ? " < > |')
    rod = Path(a.rod).resolve() if a.rod else PAKKE.parent / "trackpoint_analyser"
    mappe = rod / navn
    if mappe.exists():
        sys.exit(f"Mappen findes allerede, intet er ændret: {mappe}")

    for under in ("data/A", "data/B", "resultat"):
        (mappe / under).mkdir(parents=True)
    shutil.copyfile(SKABELONER / "config.yaml", mappe / "config.yaml")
    bat = (SKABELONER / "koer_analyse.bat").read_text(encoding="utf-8").replace("__VAERKTOEJ__", str(VAERKTOEJ))
    (mappe / "koer_analyse.bat").write_bytes(bat.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    (mappe / "Vejledning - trin for trin.txt").write_text(SAADAN.format(vaerktoej=VAERKTOEJ), encoding="utf-8")

    print(f"\nAnalysemappen er oprettet: {mappe}\n")
    print(SAADAN.format(vaerktoej=VAERKTOEJ))
    if not a.ingen_explorer and os.name == "nt":
        subprocess.run(["explorer", str(mappe)])


if __name__ == "__main__":
    main()
