#!/usr/bin/env python3
"""
Version 8: Duale Zahlenrepräsentation (String + Numerisch) für sichere Konvertierung
- LLM gibt Zahlen sowohl als Original-String als auch als konvertierte Zahl zurück
- Validierung der Konvertierung zur Fehlervermeidung
- Explizite Anweisungen für beide Formate
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


def validate_number_conversion(original: str, converted: float) -> Dict[str, Any]:
    """Validiert die Konvertierung von String zu Zahl"""
    try:
        python_converted = float(parse_german_amount(original))
        match = abs(python_converted - converted) < 0.01
        
        return {
            "original_string": original,
            "llm_converted": converted,
            "python_converted": python_converted,
            "conversion_match": match,
            "difference": abs(python_converted - converted) if not match else 0
        }
    except Exception as e:
        return {
            "original_string": original,
            "llm_converted": converted,
            "python_converted": None,
            "conversion_match": False,
            "error": str(e)
        }


def ask_llm_v8_analysis(json_file: str, 
                        ollama_url: str = "https://fs.aiora.rest",
                        model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 8: Duale Zahlenrepräsentation für sichere Konvertierung
    """
    logger.info(f"Analysiere V8 (duale Zahlenrepräsentation): {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse
    doc_text = content.get("text", "")[:20000]
    
    # Strukturierter Prompt für V8 mit dualer Zahlenrepräsentation
    question = """KONTOAUSZUG ANALYSE MIT DUALER ZAHLENREPRÄSENTATION:

🔴 WICHTIG: DUALE ZAHLENFORMAT-ANGABE
Für JEDEN Geldbetrag musst du ZWEI Werte angeben:
1. "betrag_original": Der EXAKTE String wie er im Dokument steht (mit Punkt/Komma)
2. "betrag_nummer": Die konvertierte Dezimalzahl

DEUTSCHES FORMAT KONVERTIERUNG:
- "450.105,96" → betrag_original: "450.105,96", betrag_nummer: 450105.96
- "1.234,56" → betrag_original: "1.234,56", betrag_nummer: 1234.56
- "-392,33" → betrag_original: "-392,33", betrag_nummer: -392.33
- "37.000,00" → betrag_original: "37.000,00", betrag_nummer: 37000.00

📋 EXTRAKTIONS-STRUKTUR:

1. AUSZUGSNUMMER:
Finde "Kontoauszug X/2022" → auszug_nummer: X

2. ANFANGSSALDO:
Suche "Kontostand am [DATUM], Auszug Nr. [VORHERIGE_NR]"
{
  "anfangssaldo": {
    "betrag_original": "405.107,75",  // EXAKT wie im Dokument
    "betrag_nummer": 405107.75,       // Konvertiert
    "datum": "29.04.2022",
    "referenz_auszug": "3",
    "beschreibung": "Kontostand am 29.04.2022, Auszug Nr. 3"
  }
}

3. ENDSALDO:
Suche "Kontostand am [DATUM] um [UHRZEIT] Uhr"
{
  "endsaldo": {
    "betrag_original": "450.105,96",  // EXAKT wie im Dokument
    "betrag_nummer": 450105.96,       // Konvertiert
    "datum": "31.05.2022",
    "uhrzeit": "20:03",
    "beschreibung": "Kontostand am 31.05.2022 um 20:03 Uhr"
  }
}

4. TRANSAKTIONEN:
Für JEDE Transaktion:
{
  "datum": "02.05.2022",
  "beschreibung": "Entgeltabrechnung",
  "betrag_original": "-1,95",    // EXAKT wie im Dokument
  "betrag_nummer": -1.95,         // Konvertiert
  "valuta": "30.04.2022"          // Falls vorhanden
}

5. VALIDIERUNG MIT ALLEN TRANSAKTIONEN:
Summiere ALLE betrag_nummer Werte der Transaktionen!

BEISPIEL MIT 11 TRANSAKTIONEN:
transaktionen_details = [
  {"betrag_original": "-170,86", "betrag_nummer": -170.86},
  {"betrag_original": "-1,95", "betrag_nummer": -1.95},
  {"betrag_original": "37.000,00", "betrag_nummer": 37000.00},
  {"betrag_original": "-101.046,00", "betrag_nummer": -101046.00},
  {"betrag_original": "-100.480,00", "betrag_nummer": -100480.00},
  {"betrag_original": "103.924,60", "betrag_nummer": 103924.60},
  {"betrag_original": "10.000,00", "betrag_nummer": 10000.00},
  {"betrag_original": "-11,25", "betrag_nummer": -11.25},
  {"betrag_original": "41.989,54", "betrag_nummer": 41989.54},
  {"betrag_original": "-20.000,00", "betrag_nummer": -20000.00},
  {"betrag_original": "42.689,03", "betrag_nummer": 42689.03}
]

SUMME BERECHNEN:
transaktionen_summe_berechnung = "-170.86 + (-1.95) + 37000.00 + (-101046.00) + (-100480.00) + 103924.60 + 10000.00 + (-11.25) + 41989.54 + (-20000.00) + 42689.03"
transaktionen_summe_nummer = 13893.11

validierung = {
  "anfangssaldo_nummer": 391214.64,
  "transaktionen_summe_nummer": 13893.11,
  "berechneter_endsaldo": 405107.75,
  "dokument_endsaldo_nummer": 405107.75,
  "differenz": 0.00,
  "validierung_ok": true
}

⚠️ KRITISCH: 
- NIEMALS nur erste/letzte Transaktion summieren!
- IMMER alle Transaktionen addieren!
- Original-Strings EXAKT wie im Dokument (nicht verändern!)
- Zahlen korrekt konvertieren (Punkt→nichts, Komma→Punkt)

Gib die Analyse als strukturiertes JSON zurück."""
    
    logger.info("Sende V8 Anfrage mit dualer Zahlenrepräsentation...")
    
    # Client mit custom URL
    client = ollama.Client(host=ollama_url)
    
    # Anfrage an LLM
    response = client.chat(
        model=model,
        messages=[
            {
                'role': 'system',
                'content': 'Du bist ein präziser Dokumentenanalyse-Assistent. Du musst JEDEN Betrag ZWEIMAL angeben: einmal als Original-String (betrag_original) und einmal als konvertierte Zahl (betrag_nummer).'
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
        logger.debug(f"LLM Response keys: {list(result.keys())[:10]}")
    except Exception as e:
        logger.error(f"JSON Parse Error: {e}")
        logger.error(f"Raw response: {response['message']['content'][:500]}")
        result = {}
    
    # Validiere Konvertierungen
    conversion_validations = []
    
    # Prüfe Anfangssaldo
    if isinstance(result.get("anfangssaldo"), dict):
        anfang_orig = result["anfangssaldo"].get("betrag_original", "")
        anfang_num = result["anfangssaldo"].get("betrag_nummer", 0)
        if anfang_orig:
            val = validate_number_conversion(anfang_orig, anfang_num)
            val["field"] = "anfangssaldo"
            conversion_validations.append(val)
    
    # Prüfe Endsaldo
    if isinstance(result.get("endsaldo"), dict):
        ende_orig = result["endsaldo"].get("betrag_original", "")
        ende_num = result["endsaldo"].get("betrag_nummer", 0)
        if ende_orig:
            val = validate_number_conversion(ende_orig, ende_num)
            val["field"] = "endsaldo"
            conversion_validations.append(val)
    
    # Prüfe Transaktionen
    for i, trans in enumerate(result.get("transaktionen", [])):
        if isinstance(trans, dict):
            trans_orig = trans.get("betrag_original", "")
            trans_num = trans.get("betrag_nummer", 0)
            if trans_orig:
                val = validate_number_conversion(trans_orig, trans_num)
                val["field"] = f"transaktion_{i+1}"
                conversion_validations.append(val)
    
    # Python-Validierung mit korrigierten Werten
    python_validation = validate_with_python_v8(result, conversion_validations)
    
    # Formatiere Ergebnis
    return {
        "datei": json_file,
        "auszug_nummer": result.get("auszug_nummer", ""),
        "anfangssaldo": result.get("anfangssaldo", {}),
        "endsaldo": result.get("endsaldo", {}),
        "transaktionen": result.get("transaktionen", []),
        "anzahl_transaktionen": len(result.get("transaktionen", [])),
        "validierung": result.get("validierung", {}),
        "conversion_validations": conversion_validations,
        "python_validierung": python_validation
    }


def validate_with_python_v8(llm_result: Dict, conversions: List[Dict]) -> Dict[str, Any]:
    """Python-basierte Validierung mit Konvertierungs-Korrekturen"""
    try:
        # Verwende Python-konvertierte Werte wenn LLM-Konvertierung falsch ist
        anfangssaldo = None
        endsaldo = None
        
        # Anfangssaldo
        anfang_data = llm_result.get("anfangssaldo", {})
        if isinstance(anfang_data, dict):
            # Finde Konvertierungs-Validierung
            anfang_conv = next((c for c in conversions if c["field"] == "anfangssaldo"), None)
            if anfang_conv and anfang_conv.get("python_converted") is not None:
                anfangssaldo = Decimal(str(anfang_conv["python_converted"]))
            else:
                anfangssaldo = parse_german_amount(anfang_data.get("betrag_nummer", anfang_data.get("betrag_original", 0)))
        else:
            anfangssaldo = parse_german_amount(anfang_data)
            
        # Endsaldo
        ende_data = llm_result.get("endsaldo", {})
        if isinstance(ende_data, dict):
            # Finde Konvertierungs-Validierung
            ende_conv = next((c for c in conversions if c["field"] == "endsaldo"), None)
            if ende_conv and ende_conv.get("python_converted") is not None:
                endsaldo = Decimal(str(ende_conv["python_converted"]))
            else:
                endsaldo = parse_german_amount(ende_data.get("betrag_nummer", ende_data.get("betrag_original", 0)))
        else:
            endsaldo = parse_german_amount(ende_data)
        
        # Transaktionen summieren mit korrigierten Werten
        summe = Decimal('0')
        for i, t in enumerate(llm_result.get("transaktionen", [])):
            # Finde Konvertierungs-Validierung für diese Transaktion
            trans_conv = next((c for c in conversions if c["field"] == f"transaktion_{i+1}"), None)
            if trans_conv and trans_conv.get("python_converted") is not None:
                betrag = Decimal(str(trans_conv["python_converted"]))
            elif isinstance(t, dict):
                betrag = parse_german_amount(t.get("betrag_nummer", t.get("betrag_original", 0)))
            else:
                betrag = parse_german_amount(t.get("betrag", 0))
            summe += betrag
        
        # Berechne erwarteten Endsaldo
        berechneter_saldo = anfangssaldo + summe
        differenz = abs(berechneter_saldo - endsaldo)
        
        # Zähle Konvertierungsfehler
        conversion_errors = sum(1 for c in conversions if not c.get("conversion_match", False))
        
        return {
            "anfangssaldo": float(anfangssaldo),
            "endsaldo_aus_dokument": float(endsaldo),
            "transaktionen_summe": float(summe),
            "berechneter_endsaldo": float(berechneter_saldo),
            "differenz": float(differenz),
            "validierung_ok": differenz < Decimal('0.01'),
            "formel": f"{float(anfangssaldo):.2f} + {float(summe):.2f} = {float(berechneter_saldo):.2f}",
            "conversion_errors": conversion_errors,
            "total_conversions": len(conversions)
        }
    except Exception as e:
        logger.error(f"Fehler bei Python-Validierung: {e}")
        return {
            "error": str(e),
            "validierung_ok": False
        }


def check_continuity_v8(analysen: List[Dict]) -> Dict[str, Any]:
    """Prüft Kontinuität zwischen aufeinanderfolgenden Auszügen"""
    kontinuitaet_checks = []
    
    for i in range(len(analysen) - 1):
        current = analysen[i]
        next_stmt = analysen[i + 1]
        
        # Verwende Python-validierte Werte
        current_end = current["python_validierung"]["endsaldo_aus_dokument"]
        next_start = next_stmt["python_validierung"]["anfangssaldo"]
        
        diff = abs(current_end - next_start)
        kontinuitaet_ok = diff < 0.01
        
        kontinuitaet_checks.append({
            "auszug_von": current.get("auszug_nummer", "?"),
            "auszug_nach": next_stmt.get("auszug_nummer", "?"),
            "endsaldo_von": current_end,
            "anfangssaldo_nach": next_start,
            "kontinuität_ok": kontinuitaet_ok,
            "differenz": diff
        })
    
    return {
        "kontinuität_prüfungen": kontinuitaet_checks,
        "alle_ok": all(c["kontinuität_ok"] for c in kontinuitaet_checks)
    }


def main():
    """Hauptfunktion für V8 Analyse"""
    
    parser = argparse.ArgumentParser(description='Kontoauszug Analyse V8 - Duale Zahlenrepräsentation')
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
    print("KONTOAUSZUG ANALYSE V8 - DUALE ZAHLENREPRÄSENTATION")
    print("="*80)
    print("Verbesserungen:")
    print("✓ Duale Zahlenrepräsentation (Original-String + Nummer)")
    print("✓ Validierung jeder Zahlenkonvertierung")
    print("✓ Fehlerkorrektur bei falschen LLM-Konvertierungen")
    print("✓ Detaillierte Konvertierungs-Reports")
    
    # Finde alle JSON-Dateien
    json_files = sorted(Path('.').glob('Konto_Auszug_2022_000[3-7]_result.json'))
    
    if not json_files:
        print("\n✗ Keine Kontoauszug JSON-Dateien gefunden!")
        sys.exit(1)
    
    print(f"\nGefunden: {len(json_files)} Kontoauszüge für V8 Analyse")
    
    # Sammle alle Analysen
    alle_analysen = []
    erfolgreiche_pruefungen = 0
    gesamt_konvertierungsfehler = 0
    
    # Verarbeite jede Datei
    for idx, json_file in enumerate(json_files, 1):
        print(f"\n{'='*70}")
        print(f"[{idx}/{len(json_files)}] Verarbeite: {json_file.name}")
        print(f"{'='*70}")
        
        try:
            # LLM Analyse
            analyse = ask_llm_v8_analysis(str(json_file), args.url, args.model)
            alle_analysen.append(analyse)
            
            # Zeige Ergebnisse
            print(f"\n📊 KONTOAUSZUG {analyse['auszug_nummer']}/2022")
            
            # Salden mit dualer Darstellung
            anfang = analyse.get('anfangssaldo', {})
            ende = analyse.get('endsaldo', {})
            
            if isinstance(anfang, dict):
                print(f"\n💰 ANFANGSSALDO:")
                print(f"   Original: {anfang.get('betrag_original', '?')}")
                print(f"   Konvertiert: {anfang.get('betrag_nummer', '?')}")
                print(f"   Datum: {anfang.get('datum', '?')}")
            
            if isinstance(ende, dict):
                print(f"\n💰 ENDSALDO:")
                print(f"   Original: {ende.get('betrag_original', '?')}")
                print(f"   Konvertiert: {ende.get('betrag_nummer', '?')}")
                print(f"   Datum: {ende.get('datum', '?')}")
            
            # Transaktionen
            trans = analyse['transaktionen']
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} Stück")
            
            # Konvertierungs-Validierung
            conv_vals = analyse.get('conversion_validations', [])
            if conv_vals:
                errors = [c for c in conv_vals if not c.get('conversion_match', False)]
                if errors:
                    print(f"\n⚠️  KONVERTIERUNGSFEHLER: {len(errors)}")
                    for err in errors[:3]:
                        print(f"   {err['field']}: '{err['original_string']}' → LLM: {err['llm_converted']}, Python: {err.get('python_converted', 'N/A')}")
                else:
                    print(f"\n✅ Alle Konvertierungen korrekt")
                gesamt_konvertierungsfehler += len(errors)
            
            # Validierung
            pv = analyse['python_validierung']
            if pv.get('validierung_ok'):
                print(f"\n✅ SALDENPRÜFUNG ERFOLGREICH:")
                print(f"   {pv['formel']}")
                erfolgreiche_pruefungen += 1
            else:
                print(f"\n❌ SALDENPRÜFUNG FEHLGESCHLAGEN:")
                print(f"   Differenz: {pv.get('differenz', '?'):.2f} EUR")
            
            # Konvertierungs-Statistik
            if pv.get('total_conversions', 0) > 0:
                print(f"\n📊 KONVERTIERUNGS-STATISTIK:")
                print(f"   Gesamt: {pv['total_conversions']}")
                print(f"   Fehler: {pv['conversion_errors']}")
                print(f"   Erfolgsrate: {((pv['total_conversions'] - pv['conversion_errors']) / pv['total_conversions'] * 100):.1f}%")
            
            logger.info("✓ V8 Analyse abgeschlossen")
            
        except Exception as e:
            logger.error(f"Fehler bei Verarbeitung von {json_file}: {e}")
            print(f"\n❌ Fehler: {e}")
    
    # Kontinuitätsprüfung
    if len(alle_analysen) > 1:
        print(f"\n{'='*70}")
        print("KONTINUITÄTSPRÜFUNG ZWISCHEN AUSZÜGEN")
        print(f"{'='*70}")
        
        kontinuitaet = check_continuity_v8(alle_analysen)
        for check in kontinuitaet['kontinuität_prüfungen']:
            if check['kontinuität_ok']:
                print(f"✅ Auszug {check['auszug_von']} → {check['auszug_nach']}: "
                      f"Ende {check['endsaldo_von']:.2f} = Anfang {check['anfangssaldo_nach']:.2f}")
            else:
                print(f"❌ Auszug {check['auszug_von']} → {check['auszug_nach']}: "
                      f"Differenz {check['differenz']:.2f}")
    
    # Speichere Gesamtergebnis
    ergebnis = {
        "version": "8.0",
        "beschreibung": "Duale Zahlenrepräsentation mit Konvertierungs-Validierung",
        "model": args.model,
        "verbesserungen": [
            "Duale Zahlenrepräsentation (String + Nummer)",
            "Validierung jeder Zahlenkonvertierung",
            "Automatische Korrektur falscher LLM-Konvertierungen",
            "Detaillierte Konvertierungs-Reports",
            "Robuste Fehlerbehandlung"
        ],
        "analysen": alle_analysen,
        "anzahl_dokumente": len(alle_analysen),
        "erfolgreiche_pruefungen": erfolgreiche_pruefungen,
        "gesamt_konvertierungsfehler": gesamt_konvertierungsfehler,
        "kontinuitaet": check_continuity_v8(alle_analysen) if len(alle_analysen) > 1 else None
    }
    
    output_file = "kontoauszuege_analyse_komplett_v8.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ergebnis, f, ensure_ascii=False, indent=2)
    
    # Zusammenfassung
    print(f"\n{'='*80}")
    print(f"✅ ANALYSE V8 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche_pruefungen}/{len(alle_analysen)}")
    print(f"⚠️  Gesamt Konvertierungsfehler: {gesamt_konvertierungsfehler}")
    
    if ergebnis.get('kontinuitaet', {}).get('alle_ok'):
        print(f"✅ Kontinuität zwischen allen Auszügen bestätigt")
    
    print(f"{'='*80}")


if __name__ == "__main__":
    main()