# RAW File Renamer

Tento skript je jednoduchý a efektivní desktopový nástroj (GUI), který slouží k hromadnému přejmenování RAW souborů (jako jsou .CR2, .NEF, .ARW) na základě názvů jejich odpovídajících JPG souborů. Klíčovou funkcí je **porovnávání souborů na základě vizuální podobnosti obrazu**, což zajišťuje správné spárování i v případě, že názvy souborů se neshodují.

## Klíčové vlastnosti

* **Vizuální párování:** Používá `perceptual hash` k nalezení vizuálně podobných RAW a JPG souborů.
* **Přizpůsobitelný práh podobnosti:** Umožňuje nastavit práh podobnosti pro přesnější výsledky.
* **Interaktivní GUI:** Jednoduché uživatelské rozhraní usnadňuje výběr složek a spouštění operací.
* **Generování plánu přejmenování:** Před samotným přejmenováním zobrazí navrhovaný plán, takže si ho můžete zkontrolovat.
* **Obnova ze zálohy:** Při přejmenování se automaticky vytvoří záložní log, který umožňuje snadnou obnovu původních názvů souborů.
* **Podpora více formátů:** Podporuje běžné RAW a JPG formáty souborů.

## Požadavky

Skript vyžaduje následující knihovny Pythonu, které lze nainstalovat pomocí pip:

* `Pillow`
* `imagehash`

## Jak spustit

1.  **Stáhněte si skript:** Naklonujte repozitář nebo stáhněte soubor `renamerV3_gui.py`.
2.  **Nainstalujte závislosti:** Otevřete terminál nebo příkazový řádek, přejděte do složky se skriptem a spusťte následující příkaz:

    ```bash
    pip install Pillow imagehash
    ```

3.  **Spusťte program:**

    ```bash
    python renamerV3_gui.py
    ```

Po spuštění se otevře grafické rozhraní, ve kterém můžete pokračovat.

## Používání GUI

1.  **Vyberte složky:** Pomocí tlačítka `Procházet...` vyberte složky s RAW a JPG soubory.
2.  **Nastavte práh podobnosti:** Pomocí posuvníku upravte práh podobnosti, pokud je to potřeba. Nižší hodnota znamená přesnější shodu.
3.  **Skenovat soubory:** Klikněte na tlačítko `Skenovat soubory` k nalezení všech RAW a JPG souborů ve vybraných složkách.
4.  **Najít páry:** Klikněte na `Najít páry`. Skript provede analýzu a zobrazí nalezené shody v tabulce.
5.  **Přejmenovat:** Pokud jste s navrhovaným plánem spokojeni, klikněte na `Přejmenovat`. Všechny RAW soubory budou přejmenovány.
6.  **Obnovit:** V případě potřeby můžete použít tlačítko `Obnovit ze zálohy` k vrácení původních názvů souborů pomocí automaticky vytvořeného logu.
