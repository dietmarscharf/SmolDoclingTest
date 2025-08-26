#!/usr/bin/env python3
"""
Version 7: Korrigierte LLM-Summierung in schritt5_validierung
- Explizite Anweisungen für korrekte Transaktionssummierung
- Detaillierte Beispiele für Mehrfach-Transaktionen
- Verbesserte Validierungslogik
"""

import json
import sys
import re
from pathlib import Path
import ollama
from typing import Dict, Any, List, Optional, Tuple
import logging
from decimal import Decimal
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_german_amount(amount_str: str) -> Decimal:
    """Konvertiert deutschen Betrag zu Decimal - erkennt automatisch das Format"""
    if isinstance(amount_str, (int, float)):
        return Decimal(str(amount_str))
        
    amount_str = str(amount_str).replace('EUR', '').strip().replace('+', '').replace(' ', '')
    
    # Erkenne Format automatisch:
    # Deutsches Format: 450.105,96 (Punkt für Tausender, Komma für Dezimal)
    # Englisches Format: 450105.96 (Punkt für Dezimal)
    # String-Zahlen wie "405107.75" könnten beides sein!
    
    # Zähle Punkte und Kommas
    num_dots = amount_str.count('.')
    num_commas = amount_str.count(',')
    
    # Entscheide basierend auf Pattern
    if num_commas == 1 and num_dots <= 1:
        # Deutsches Format: 450.105,96 oder 450105,96
        if num_dots == 1:
            # Prüfe Position: Punkt sollte vor Komma sein
            dot_pos = amount_str.index('.')
            comma_pos = amount_str.index(',')
            if dot_pos < comma_pos:
                # Deutsches Format mit Tausendertrennzeichen
                amount_str = amount_str.replace('.', '').replace(',', '.')
            else:
                # Ungewöhnlich, behandle als englisch
                amount_str = amount_str.replace(',', '')
        else:
            # Nur Komma, definitiv deutsch
            amount_str = amount_str.replace(',', '.')
    elif num_dots == 1 and num_commas == 0:
        # Könnte englisch ODER deutsch ohne Dezimalstellen sein
        # Prüfe ob es wie eine große Zahl aussieht
        parts = amount_str.split('.')
        if len(parts) == 2 and len(parts[1]) == 2:
            # Wahrscheinlich englisches Format (z.B. 405107.75)
            pass  # Nichts tun, ist schon richtig
        elif len(parts) == 2 and len(parts[1]) == 3:
            # Wahrscheinlich deutsches Format (z.B. 405.107)
            amount_str = amount_str.replace('.', '')
        else:
            # Unsicher, lasse wie es ist
            pass
    elif num_dots > 1:
        # Mehrere Punkte = deutsches Format mit Tausendertrennzeichen
        amount_str = amount_str.replace('.', '').replace(',', '.')
    
    try:
        return Decimal(amount_str)
    except:
        logger.warning(f"Konnte Betrag nicht parsen: {amount_str}")
        return Decimal('0')


def extract_valuta_date(description: str) -> Optional[str]:
    """Extrahiert Valuta-Datum aus Beschreibung"""
    patterns = [
        r'Wert:\s*(\d{2}\.\d{2}\.\d{4})',
        r'Valuta:\s*(\d{2}\.\d{2}\.\d{4})',
        r'/\s*Wert:\s*(\d{2}\.\d{2}\.\d{4})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    return None


def classify_transaction_type(description: str, betrag: Decimal) -> str:
    """Klassifiziert Transaktionsart basierend auf Beschreibung"""
    desc_lower = description.lower()
    
    # Detaillierte Klassifikation
    if 'wertpapierabrechnung' in desc_lower or 'wertp.' in desc_lower:
        if 'vv' in description or 'verkauf' in desc_lower:
            return 'Wertpapierverkauf'
        elif 'kv' in description or 'kauf' in desc_lower:
            return 'Wertpapierkauf'
        else:
            return 'Wertpapierabrechnung'
    elif 'durchlfd' in desc_lower and 'sperrbetr' in desc_lower:
        return 'Wertpapier-Sperrbeträge'
    elif 'überweisung' in desc_lower or 'übertrag' in desc_lower:
        return 'Überweisung ausgehend' if betrag < 0 else 'Überweisung eingehend'
    elif 'gutschriftseingang' in desc_lower:
        return 'Gutschrift'
    elif 'lastschr' in desc_lower:
        return 'Lastschrift'
    elif 'depotentgelt' in desc_lower:
        return 'Depotentgelt'
    elif 'entgeltabrechnung' in desc_lower:
        return 'Entgeltabrechnung'
    elif 'abrechnung' in desc_lower:
        if 'verwahrentgelt' in desc_lower:
            return 'Verwahrentgelt'
        else:
            return 'Abrechnung'
    elif betrag > 0:
        return 'Eingang'
    else:
        return 'Ausgang'


def extract_wkn_isin(description: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrahiert WKN, ISIN und Wertpapiername"""
    wkn = None
    isin = None
    name = None
    
    # WKN
    wkn_match = re.search(r'WKN\s+([A-Z0-9]{6})', description)
    if wkn_match:
        wkn = wkn_match.group(1)
    
    # ISIN
    isin_match = re.search(r'([A-Z]{2}[A-Z0-9]{10})', description)
    if isin_match:
        isin = isin_match.group(1)
    
    # Wertpapiername (Tesla, etc.)
    if 'TESLA INC' in description.upper():
        name = 'TESLA INC.'
    
    return wkn, isin, name


def ask_llm_v7_analysis(json_file: str, 
                        ollama_url: str = "https://fs.aiora.rest",
                        model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 7: Korrigierte LLM-Summierung mit expliziten Anweisungen
    """
    logger.info(f"Analysiere V7 (korrigierte Summierung): {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse
    doc_text = content.get("text", "")[:20000]
    
    # Strukturierter Prompt für V7 mit verbesserter Summierung
    question = """SCHRITT-FÜR-SCHRITT ANLEITUNG FÜR DEUTSCHE KONTOAUSZÜGE:

🔴 KRITISCH - DEUTSCHES ZAHLENFORMAT:
- "450.105,96" = 450105.96 (vierhundertfünfzigtausend)
- "1.234,56" = 1234.56 (eintausend)
- Punkt = Tausender (ENTFERNEN!), Komma = Dezimal (zu Punkt!)

📋 SCHRITT 1: FINDE DIE AUSZUGSNUMMER
Suche in der Kopfzeile nach: "Kontoauszug X/2022"
Beispiele:
- "Kontoauszug 3/2022" → Auszugsnummer = 3
- "Kontoauszug 4/2022" → Auszugsnummer = 4
- "Kontoauszug 5/2022" → Auszugsnummer = 5

📋 SCHRITT 2: FINDE DEN ANFANGSSALDO
Muster: "Kontostand am [DATUM], Auszug Nr. [VORHERIGE_NR]"
WICHTIG: Die Auszugsnummer im Anfangssaldo ist IMMER die VORHERIGE!

Beispiele für korrekte Zuordnung:
- Kontoauszug 3/2022 → Anfang: "Kontostand am 31.03.2022, Auszug Nr. 2"
- Kontoauszug 4/2022 → Anfang: "Kontostand am 29.04.2022, Auszug Nr. 3"
- Kontoauszug 5/2022 → Anfang: "Kontostand am 31.05.2022, Auszug Nr. 4"
- Kontoauszug 6/2022 → Anfang: "Kontostand am 30.06.2022, Auszug Nr. 5"
- Kontoauszug 7/2022 → Anfang: "Kontostand am 29.07.2022, Auszug Nr. 6"

📋 SCHRITT 3: FINDE DEN ENDSALDO
Muster: "Kontostand am [DATUM] um [UHRZEIT] Uhr"
Dies steht IMMER am Ende des Transaktionsbereichs

📋 SCHRITT 4: EXTRAHIERE NUR ECHTE TRANSAKTIONEN
WICHTIG: NICHT als Transaktionen zählen:
- Zeilen mit "Kontostand am..." (das sind Salden!)
- Zeilen mit "Auszug Nr..." (das sind Referenzen!)
- "Anzahl Anlagen" (das ist eine Info)

NUR echte Bewegungen wie:
- Entgeltabrechnung
- Überweisung/Übertrag
- Gutschriftseingang
- Wertpapierabrechnung
- Lastschrift
- Abrechnung

📋 SCHRITT 5: VALIDIERUNG MIT KORREKTER SUMMIERUNG
⚠️ KRITISCH: Du MUSST ALLE Transaktionen summieren, nicht nur die erste oder letzte!

BEISPIEL MIT 11 TRANSAKTIONEN (wie Auszug 3):
```
Transaktion 1: -170.86
Transaktion 2: -1.95
Transaktion 3: +37000.00
Transaktion 4: -101046.00
Transaktion 5: -100480.00
Transaktion 6: +103924.60
Transaktion 7: +10000.00
Transaktion 8: -11.25
Transaktion 9: +41989.54
Transaktion 10: -20000.00
Transaktion 11: +42689.03

SUMME ALLER TRANSAKTIONEN:
= -170.86 + (-1.95) + 37000.00 + (-101046.00) + (-100480.00) + 103924.60 + 10000.00 + (-11.25) + 41989.54 + (-20000.00) + 42689.03
= 13893.11
```

BEISPIEL MIT 3 TRANSAKTIONEN (wie Auszug 4):
```
Transaktion 1: -1.95
Transaktion 2: -23700.00
Transaktion 3: +68700.16

SUMME ALLER TRANSAKTIONEN:
= -1.95 + (-23700.00) + 68700.16
= 44998.21
```

VALIDIERUNG:
Anfangssaldo + SUMME(ALLE Transaktionen) = Endsaldo
391214.64 + 13893.11 = 405107.75 ✓

⚠️ FALSCH wäre:
391214.64 + (-170.86) = 391043.78 ❌ (nur erste Transaktion)
391214.64 + 42689.03 = 433903.67 ❌ (nur letzte Transaktion)

WICHTIGE FELDER IN DER VALIDIERUNG:
- "plus_transaktionen": MUSS die SUMME ALLER Transaktionen sein!
- "transaktionen_summe": MUSS identisch mit "plus_transaktionen" sein!

Extrahiere in strukturiertem JSON-Format.
"""
    
    logger.info("Sende V7 Anfrage mit korrigierter Summierungslogik...")
    
    # Client mit custom URL
    client = ollama.Client(host=ollama_url)
    
    # Anfrage an LLM
    response = client.chat(
        model=model,
        messages=[
            {
                'role': 'system',
                'content': 'Du bist ein präziser Dokumentenanalyse-Assistent für deutsche Kontoauszüge. Du MUSST beim Summieren ALLE Transaktionen addieren, nicht nur einzelne!'
            },
            {
                'role': 'user', 
                'content': f"Dokument:\n{doc_text}\n\nAufgabe:\n{question}"
            }
        ],
        format='json',
        options={
            'temperature': 0.1,
            'num_predict': 4000
        }
    )
    
    # Parse Antwort
    try:
        result = json.loads(response['message']['content'])
        # Debug: zeige was LLM zurückgibt
        logger.debug(f"LLM Response keys: {list(result.keys())[:5]}")
        logger.debug(f"Anfangssaldo type: {type(result.get('anfangssaldo'))}")
    except Exception as e:
        logger.error(f"JSON Parse Error: {e}")
        logger.error(f"Raw response: {response['message']['content'][:500]}")
        result = {}
    
    # Extrahiere Statement-Nummer aus Dateiname
    match = re.search(r'(\d{4})_result\.json', json_file)
    stmt_num = match.group(1) if match else "unbekannt"
    
    # Python-Validierung
    python_validation = validate_with_python(result)
    
    # Konvertiere LLM-Antwort in einheitliches Format
    # Handle verschiedene Antwortformate vom LLM
    anfangssaldo_raw = result.get("anfangssaldo", {})
    if isinstance(anfangssaldo_raw, (int, float)):
        anfangssaldo_dict = {
            "betrag": anfangssaldo_raw,
            "betrag_text": f"{anfangssaldo_raw:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            "datum": result.get("anfangssaldo_datum", ""),
            "auszug_nr_referenz": result.get("anfangssaldo_referenz", ""),
            "beschreibung": result.get("anfangssaldo_beschreibung", "")
        }
    else:
        anfangssaldo_dict = anfangssaldo_raw
        
    endsaldo_raw = result.get("endsaldo", {})
    if isinstance(endsaldo_raw, (int, float)):
        endsaldo_dict = {
            "betrag": endsaldo_raw,
            "betrag_text": f"{endsaldo_raw:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            "datum": result.get("endsaldo_datum", ""),
            "uhrzeit": result.get("endsaldo_uhrzeit", ""),
            "beschreibung": result.get("endsaldo_beschreibung", "")
        }
    else:
        endsaldo_dict = endsaldo_raw
    
    return {
        "datei": json_file,
        "schritt1_auszugsnummer": result.get("schritt1_auszugsnummer", result.get("auszugsnummer", "")),
        "auszug_nummer": result.get("auszug_nummer", result.get("auszugsnummer", "")),
        "kontodaten": result.get("kontodaten", {}),
        "schritt2_anfangssaldo": result.get("schritt2_anfangssaldo", ""),
        "anfangssaldo": anfangssaldo_dict,
        "schritt3_endsaldo": result.get("schritt3_endsaldo", ""),
        "endsaldo": endsaldo_dict,
        "schritt4_transaktionen": result.get("schritt4_transaktionen", ""),
        "transaktionen": result.get("transaktionen", []),
        "anzahl_transaktionen": len(result.get("transaktionen", [])),
        "transaktionen_summe": result.get("transaktionen_summe", 0),
        "schritt5_validierung": result.get("schritt5_validierung", result.get("validierung", {})),
        "python_validierung": python_validation
    }


def validate_with_python(llm_result: Dict) -> Dict[str, Any]:
    """Python-basierte Validierung der LLM-Ergebnisse"""
    try:
        # Extrahiere Daten - handle verschiedene Datentypen
        anfangssaldo_data = llm_result.get("anfangssaldo", {})
        if isinstance(anfangssaldo_data, (int, float, str)):
            anfangssaldo = parse_german_amount(anfangssaldo_data)
        else:
            anfangssaldo = parse_german_amount(anfangssaldo_data.get("betrag", 0))
            
        endsaldo_data = llm_result.get("endsaldo", {})
        if isinstance(endsaldo_data, (int, float, str)):
            endsaldo = parse_german_amount(endsaldo_data)
        else:
            endsaldo = parse_german_amount(endsaldo_data.get("betrag", 0))
            
        transaktionen = llm_result.get("transaktionen", [])
        
        # Berechne Summe aller Transaktionen
        summe = Decimal('0')
        for t in transaktionen:
            betrag = parse_german_amount(t.get("betrag", 0))
            summe += betrag
        
        # Berechne erwarteten Endsaldo
        berechneter_saldo = anfangssaldo + summe
        differenz = abs(berechneter_saldo - endsaldo)
        
        return {
            "anfangssaldo": float(anfangssaldo),
            "endsaldo_aus_dokument": float(endsaldo),
            "transaktionen_summe": float(summe),
            "berechneter_endsaldo": float(berechneter_saldo),
            "differenz": float(differenz),
            "validierung_ok": differenz < Decimal('0.01'),
            "formel": f"{float(anfangssaldo):.2f} + {float(summe):.2f} = {float(berechneter_saldo):.2f}"
        }
    except Exception as e:
        logger.error(f"Fehler bei Python-Validierung: {e}")
        return {
            "error": str(e),
            "validierung_ok": False
        }


def check_continuity(analysen: List[Dict]) -> Dict[str, Any]:
    """Prüft Kontinuität zwischen aufeinanderfolgenden Auszügen"""
    kontinuitaet_checks = []
    
    for i in range(len(analysen) - 1):
        current = analysen[i]
        next_stmt = analysen[i + 1]
        
        # Handle verschiedene Datentypen für endsaldo
        current_end_data = current.get("endsaldo", {})
        if isinstance(current_end_data, (int, float, str)):
            current_end = parse_german_amount(current_end_data)
        else:
            current_end = parse_german_amount(current_end_data.get("betrag", 0))
            
        # Handle verschiedene Datentypen für anfangssaldo
        next_start_data = next_stmt.get("anfangssaldo", {})
        if isinstance(next_start_data, (int, float, str)):
            next_start = parse_german_amount(next_start_data)
        else:
            next_start = parse_german_amount(next_start_data.get("betrag", 0))
        
        diff = abs(current_end - next_start)
        kontinuitaet_ok = diff < Decimal('0.01')
        
        kontinuitaet_checks.append({
            "auszug_von": current.get("auszug_nummer", "?"),
            "auszug_nach": next_stmt.get("auszug_nummer", "?"),
            "endsaldo_von": float(current_end),
            "anfangssaldo_nach": float(next_start),
            "kontinuität_ok": kontinuitaet_ok,
            "differenz": float(diff)
        })
    
    return {
        "kontinuität_prüfungen": kontinuitaet_checks,
        "alle_ok": all(c["kontinuität_ok"] for c in kontinuitaet_checks)
    }


def main():
    """Hauptfunktion für V7 Analyse"""
    
    parser = argparse.ArgumentParser(description='Kontoauszug Analyse V7 - Korrigierte Summierung')
    parser.add_argument('--model', default='qwen3:8b', help='Ollama Model (default: qwen3:8b)')
    parser.add_argument('--url', default='https://fs.aiora.rest', help='Ollama URL')
    args = parser.parse_args()
    
    print("\nTeste Ollama Verbindung...")
    client = ollama.Client(host=args.url)
    
    try:
        # Teste Verbindung
        models = client.list()
        print("✓ Ollama verfügbar")
    except Exception as e:
        print(f"✗ Ollama nicht erreichbar: {e}")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V7 - KORRIGIERTE SUMMIERUNG")
    print("="*80)
    print("Verbesserungen:")
    print("✓ Explizite Anweisungen für Transaktionssummierung")
    print("✓ Detaillierte Beispiele mit Mehrfach-Transaktionen")
    print("✓ Verbesserte Validierungslogik")
    print("✓ Korrekte Berechnung von plus_transaktionen")
    
    # Finde alle JSON-Dateien
    json_files = sorted(Path('.').glob('Konto_Auszug_2022_000[3-7]_result.json'))
    
    if not json_files:
        print("\n✗ Keine Kontoauszug JSON-Dateien gefunden!")
        sys.exit(1)
    
    print(f"\nGefunden: {len(json_files)} Kontoauszüge für V7 Analyse")
    
    # Sammle alle Analysen
    alle_analysen = []
    erfolgreiche_pruefungen = 0
    
    # Verarbeite jede Datei
    for idx, json_file in enumerate(json_files, 1):
        print(f"\n{'='*70}")
        print(f"[{idx}/{len(json_files)}] Verarbeite: {json_file.name}")
        print(f"{'='*70}")
        
        try:
            # LLM Analyse
            analyse = ask_llm_v7_analysis(str(json_file), args.url, args.model)
            alle_analysen.append(analyse)
            
            # Zeige Ergebnisse
            print(f"\n📊 KONTOAUSZUG {analyse['auszug_nummer']}/2022")
            
            # Salden
            anfang = analyse['anfangssaldo']
            ende = analyse['endsaldo']
            print(f"\n💰 ANFANGSSALDO (Auszug Nr. {anfang.get('auszug_nr_referenz', '?')}):")
            print(f"   {anfang.get('betrag_text', '?')} vom {anfang.get('datum', '?')}")
            
            print(f"\n💰 ENDSALDO:")
            print(f"   {ende.get('betrag_text', '?')} vom {ende.get('datum', '?')}")
            
            # Transaktionen
            trans = analyse['transaktionen']
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} Stück")
            
            # Erste 3 Transaktionen zeigen
            for t in trans[:3]:
                print(f"   {t.get('buchungsdatum', '?')}: {t.get('betrag_text', '?')} - {t.get('art', '?')}")
            if len(trans) > 3:
                print(f"   ... und {len(trans) - 3} weitere")
            
            # Validierung
            pv = analyse['python_validierung']
            if pv.get('validierung_ok'):
                print(f"\n✅ SALDENPRÜFUNG ERFOLGREICH:")
                print(f"   {pv['formel']}")
                erfolgreiche_pruefungen += 1
            else:
                print(f"\n❌ SALDENPRÜFUNG FEHLGESCHLAGEN:")
                print(f"   Differenz: {pv.get('differenz', '?'):.2f} EUR")
            
            # V7: Zeige LLM vs Python Summierung
            llm_val = analyse.get('schritt5_validierung', {})
            if llm_val:
                llm_summe = llm_val.get('plus_transaktionen', 'N/A')
                python_summe = pv.get('transaktionen_summe', 0)
                
                print(f"\n🔍 SUMMIERUNGS-VERGLEICH:")
                print(f"   LLM Summe:    {llm_summe}")
                print(f"   Python Summe: {python_summe:.2f}")
                
                if isinstance(llm_summe, (int, float)):
                    if abs(llm_summe - python_summe) < 0.01:
                        print(f"   ✅ Summierung korrekt!")
                    else:
                        print(f"   ❌ Summierungsfehler: Differenz = {abs(llm_summe - python_summe):.2f}")
            
            logger.info("✓ V7 Analyse abgeschlossen")
            
        except Exception as e:
            logger.error(f"Fehler bei Verarbeitung von {json_file}: {e}")
            print(f"\n❌ Fehler: {e}")
    
    # Kontinuitätsprüfung
    if len(alle_analysen) > 1:
        print(f"\n{'='*70}")
        print("KONTINUITÄTSPRÜFUNG ZWISCHEN AUSZÜGEN")
        print(f"{'='*70}")
        
        kontinuitaet = check_continuity(alle_analysen)
        for check in kontinuitaet['kontinuität_prüfungen']:
            if check['kontinuität_ok']:
                print(f"✅ Auszug {check['auszug_von']} → {check['auszug_nach']}: "
                      f"Ende {check['endsaldo_von']:.2f} = Anfang {check['anfangssaldo_nach']:.2f}")
            else:
                print(f"❌ Auszug {check['auszug_von']} → {check['auszug_nach']}: "
                      f"Differenz {check['differenz']:.2f}")
    
    # Speichere Gesamtergebnis
    ergebnis = {
        "version": "7.0",
        "beschreibung": "Korrigierte LLM-Summierung mit expliziten Anweisungen",
        "model": args.model,
        "verbesserungen": [
            "Explizite Summierungsanweisungen für LLM",
            "Detaillierte Beispiele mit Mehrfach-Transaktionen",
            "Korrekte Berechnung von plus_transaktionen",
            "Vergleich LLM vs Python Summierung",
            "Verbesserte Fehlerdiagnose"
        ],
        "analysen": alle_analysen,
        "anzahl_dokumente": len(alle_analysen),
        "erfolgreiche_pruefungen": erfolgreiche_pruefungen,
        "kontinuitaet": check_continuity(alle_analysen) if len(alle_analysen) > 1 else None
    }
    
    output_file = "kontoauszuege_analyse_komplett_v7.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ergebnis, f, ensure_ascii=False, indent=2)
    
    # Zusammenfassung
    print(f"\n{'='*80}")
    print(f"✅ ANALYSE V7 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche_pruefungen}/{len(alle_analysen)}")
    
    if ergebnis.get('kontinuitaet', {}).get('alle_ok'):
        print(f"✅ Kontinuität zwischen allen Auszügen bestätigt")
    
    print(f"{'='*80}")


if __name__ == "__main__":
    main()