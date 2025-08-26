#!/usr/bin/env python3
"""
Version 4: Erweiterte Transaktionsanalyse mit Kategorisierung und Valuta-Datum
- Explizite Transaktionsarten
- Valuta-Datum Extraktion
- Verwendung von qwen3:30b für bessere Ergebnisse
- Deutsches Zahlenformat (1.234,56 EUR)
"""

import json
import sys
import re
from pathlib import Path
import ollama
from typing import Dict, Any, List, Optional, Tuple
import logging
from decimal import Decimal
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_german_amount(amount_str: str) -> Decimal:
    """
    Konvertiert deutschen Betrag zu Decimal
    Beispiele: "391.214,64" -> 391214.64
    """
    if isinstance(amount_str, (int, float)):
        return Decimal(str(amount_str))
        
    amount_str = str(amount_str).replace('EUR', '').strip()
    amount_str = amount_str.replace('.', '').replace(',', '.')
    
    try:
        return Decimal(amount_str)
    except:
        logger.warning(f"Konnte Betrag nicht parsen: {amount_str}")
        return Decimal('0')


def extract_valuta_date(description: str) -> Optional[str]:
    """
    Extrahiert Valuta-Datum aus Beschreibung
    Sucht nach Patterns wie "Wert: 08.04.2022" oder "Valuta: 08.04.2022"
    """
    # Verschiedene Patterns für Valuta
    patterns = [
        r'Wert:\s*(\d{2}\.\d{2}\.\d{4})',
        r'Valuta:\s*(\d{2}\.\d{2}\.\d{4})',
        r'Wert\s+(\d{2}\.\d{2}\.\d{4})',
        r'/\s*Wert:\s*(\d{2}\.\d{2}\.\d{4})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    
    return None


def classify_transaction_type(description: str, betrag: Decimal) -> str:
    """
    Klassifiziert Transaktionsart basierend auf Beschreibung
    """
    desc_lower = description.lower()
    
    # Kategorisierungs-Regeln
    if 'wertpapier' in desc_lower or 'depot' in desc_lower or 'wertp.' in desc_lower:
        if betrag < 0:
            return 'Wertpapierkauf'
        else:
            return 'Wertpapierverkauf'
    elif 'überweisung' in desc_lower or 'übertrag' in desc_lower:
        if betrag < 0:
            return 'Überweisung ausgehend'
        else:
            return 'Überweisung eingehend'
    elif 'gutschrift' in desc_lower:
        return 'Gutschrift'
    elif 'lastschr' in desc_lower or 'lastschrift' in desc_lower:
        return 'Lastschrift'
    elif 'entgelt' in desc_lower or 'gebühr' in desc_lower or 'kosten' in desc_lower:
        return 'Gebühren'
    elif 'abrechnung' in desc_lower:
        if 'verwahrentgelt' in desc_lower:
            return 'Verwahrentgelt'
        else:
            return 'Abrechnung'
    elif 'zins' in desc_lower:
        return 'Zinsen'
    elif betrag > 0:
        return 'Eingang'
    else:
        return 'Ausgang'


def extract_wkn_isin(description: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrahiert WKN und ISIN aus Beschreibung
    """
    wkn = None
    isin = None
    
    # WKN Pattern (meist 6 Zeichen alphanumerisch)
    wkn_match = re.search(r'WKN\s+([A-Z0-9]{6})', description)
    if wkn_match:
        wkn = wkn_match.group(1)
    
    # ISIN Pattern (12 Zeichen, beginnt mit 2 Buchstaben)
    isin_match = re.search(r'([A-Z]{2}[A-Z0-9]{10})', description)
    if isin_match:
        isin = isin_match.group(1)
    
    return wkn, isin


def ask_llm_detailed_analysis_v4(json_file: str, 
                                 ollama_url: str = "https://fs.aiora.rest",
                                 model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 4: Erweiterte Analyse mit Transaktionskategorisierung und Valuta
    Nutzt qwen3:30b für bessere Ergebnisse
    """
    logger.info(f"Analysiere V4 mit {model}: {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse
    doc_text = content.get("text", "")[:20000]  # Mehr Text für 30b Modell
    
    # Detaillierte Anweisungen für V4
    question = """KRITISCH WICHTIG - DEUTSCHES DOKUMENT MIT EUROPÄISCHEM ZAHLENFORMAT:

ZAHLENFORMAT:
- PUNKT (.) = Tausendertrennzeichen → ENTFERNEN für JSON!
- KOMMA (,) = Dezimaltrennzeichen → zu PUNKT (.) für JSON!
- "391.214,64 EUR" → JSON: 391214.64
- "-101.046,00 EUR" → JSON: -101046.00

AUFGABE: Extrahiere ALLE Details aus diesem deutschen Kontoauszug:

1. KONTODATEN:
   - Kontonummer (z.B. "21503990")
   - Bank/Sparkasse
   - Kontoinhaber (z.B. "BLUEITS GmbH")

2. SALDEN:
   - ANFANGSSALDO: Erster "Kontostand am" VOR den Transaktionen
   - ENDSALDO: Letzter "Kontostand am" NACH den Transaktionen

3. JEDE TRANSAKTION mit:
   - Buchungsdatum (TT.MM.JJJJ)
   - Valuta/Wertstellung falls vorhanden (suche "Wert:" oder "Valuta:")
   - Transaktionsart (kategorisiere basierend auf Text)
   - Vollständige Beschreibung
   - Betrag als DEZIMALZAHL
   - Bei Wertpapieren: WKN, ISIN, Name extrahieren
   - Auftraggeber/Empfänger wenn erkennbar

4. TRANSAKTIONSARTEN (klassifiziere):
   - Wertpapierkauf (negative Wertpapierabrechnung)
   - Wertpapierverkauf (positive Wertpapierabrechnung)
   - Überweisung eingehend/ausgehend
   - Gutschrift
   - Lastschrift
   - Gebühren/Entgelte
   - Verwahrentgelt
   - Zinsen

5. PRÜFUNG:
   Anfangssaldo + Summe(alle Transaktionen) = Endsaldo?"""
    
    prompt = f"""Du bist ein erfahrener deutscher Bankprüfer. Analysiere diesen DEUTSCHEN Kontoauszug präzise:

{doc_text}

{question}

Antworte im folgenden JSON Format mit AMERIKANISCHEN Dezimalzahlen:
{{
    "datei": "{Path(json_file).name}",
    "kontodaten": {{
        "kontonummer": "21503990",
        "kontoinhaber": "BLUEITS GmbH",
        "bank": "Sparkasse Amberg-Sulzbach",
        "kontoart": "Geldmarktkonto"
    }},
    "zeitraum": {{
        "von": "01.04.2022",
        "bis": "29.04.2022"
    }},
    "anfangssaldo": {{
        "betrag": 391214.64,
        "betrag_original": "391.214,64 EUR",
        "datum": "31.03.2022",
        "beschreibung": "Kontostand am 31.03.2022, Auszug Nr. 2"
    }},
    "endsaldo": {{
        "betrag": 405107.75,
        "betrag_original": "405.107,75 EUR",
        "datum": "29.04.2022",
        "uhrzeit": "20:03",
        "beschreibung": "Kontostand am 29.04.2022 um 20:03 Uhr"
    }},
    "transaktionen": [
        {{
            "nr": 1,
            "buchungsdatum": "01.04.2022",
            "valuta": null,
            "art": "Verwahrentgelt",
            "beschreibung": "Abrechnung 31.03.2022 siehe Anlage Nr. 1",
            "betrag": -170.86,
            "betrag_original": "-170,86",
            "details": {{
                "anlage_nr": "1",
                "typ": "Abrechnung"
            }}
        }},
        {{
            "nr": 2,
            "buchungsdatum": "07.04.2022",
            "valuta": "08.04.2022",
            "art": "Wertpapierkauf",
            "beschreibung": "Wertpapierabrechnung / Wert: 08.04.2022 SPK AMBERG-SULZ DEPOT 7274079...",
            "betrag": -101046.00,
            "betrag_original": "-101.046,00",
            "wertpapier": {{
                "name": "TESLA INC. DL -,001",
                "wkn": "A1CX3T",
                "isin": "US88160R1014",
                "geschaeftsart": "KV"
            }},
            "depot_nr": "7274079"
        }}
    ],
    "zusammenfassung": {{
        "anzahl_transaktionen": 11,
        "transaktionen_summe": 13893.11,
        "berechneter_endsaldo": 405107.75,
        "saldo_korrekt": true,
        "differenz": 0.00
    }},
    "transaktionsarten_uebersicht": {{
        "Wertpapierkauf": 2,
        "Wertpapierverkauf": 3,
        "Überweisungen": 2,
        "Gutschriften": 2,
        "Gebühren": 2
    }},
    "wertpapiere": [
        {{
            "name": "TESLA INC.",
            "wkn": "A1CX3T",
            "isin": "US88160R1014",
            "depot": "7274079"
        }}
    ]
}}

WICHTIG: 
- Erfasse ALLE Transaktionen vollständig
- Konvertiere deutsche Zahlen korrekt
- Extrahiere Valuta-Daten wo vorhanden
- Kategorisiere Transaktionsarten präzise"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende V4 Anfrage an {model} (größeres Modell für bessere Ergebnisse)...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """Du bist ein präziser deutscher Bankprüfer mit folgenden Aufgaben:
1. Deutsche Zahlen (1.234,56) IMMER in JSON-Format (1234.56) konvertieren
2. Transaktionsarten intelligent kategorisieren
3. Valuta-Daten aus "Wert:" oder "Valuta:" extrahieren
4. WKN/ISIN von Wertpapieren erfassen
5. ALLE Transaktionen vollständig erfassen und Salden prüfen"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={
                "temperature": 0.01,
                "top_p": 1.0,
                "num_predict": 16384,  # Mehr Token für 30b Modell
                "num_ctx": 32768  # Größerer Context für 30b
            }
        )
        
        if response and 'message' in response:
            try:
                result = json.loads(response['message']['content'])
                
                # Nachbearbeitung und Validierung
                if 'transaktionen' in result:
                    for trans in result['transaktionen']:
                        # Valuta aus Beschreibung extrahieren falls nicht vorhanden
                        if not trans.get('valuta') and 'beschreibung' in trans:
                            valuta = extract_valuta_date(trans['beschreibung'])
                            if valuta:
                                trans['valuta'] = valuta
                        
                        # Transaktionsart verfeinern
                        if 'art' not in trans and 'beschreibung' in trans:
                            betrag = parse_german_amount(str(trans.get('betrag', 0)))
                            trans['art'] = classify_transaction_type(trans['beschreibung'], betrag)
                        
                        # WKN/ISIN extrahieren
                        if 'beschreibung' in trans:
                            wkn, isin = extract_wkn_isin(trans['beschreibung'])
                            if wkn or isin:
                                if 'wertpapier' not in trans:
                                    trans['wertpapier'] = {}
                                if wkn:
                                    trans['wertpapier']['wkn'] = wkn
                                if isin:
                                    trans['wertpapier']['isin'] = isin
                
                # Python-Validierung
                try:
                    anfang = Decimal(str(result.get('anfangssaldo', {}).get('betrag', 0)))
                    ende = Decimal(str(result.get('endsaldo', {}).get('betrag', 0)))
                    
                    trans_summe = Decimal('0')
                    for trans in result.get('transaktionen', []):
                        trans_summe += Decimal(str(trans.get('betrag', 0)))
                    
                    berechnet = anfang + trans_summe
                    differenz = ende - berechnet
                    
                    result['validierung'] = {
                        'anfangssaldo': float(anfang),
                        'transaktionen_summe': float(trans_summe),
                        'berechneter_endsaldo': float(berechnet),
                        'tatsaechlicher_endsaldo': float(ende),
                        'differenz': float(differenz),
                        'saldo_korrekt': abs(differenz) < Decimal('0.01')
                    }
                    
                    if abs(differenz) < Decimal('0.01'):
                        logger.info("✅ Saldenprüfung V4 erfolgreich!")
                    else:
                        logger.warning(f"⚠️ V4 Saldendifferenz: {differenz:.2f} EUR")
                        
                except Exception as e:
                    result['validierung'] = {'fehler': str(e)}
                
                logger.info("✓ V4 Analyse erfolgreich abgeschlossen")
                return result
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON Parsing fehlgeschlagen: {e}")
                return {
                    "datei": Path(json_file).name,
                    "fehler": "JSON Parsing Error",
                    "details": str(e)
                }
    
    except Exception as e:
        logger.error(f"Fehler bei LLM Anfrage: {e}")
        return {
            "datei": Path(json_file).name,
            "fehler": str(e)
        }


def analyze_all_kontoauszuege_v4():
    """
    Version 4: Erweiterte Analyse mit Kategorisierung und qwen3:30b
    """
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V4 - ERWEITERTE TRANSAKTIONSDETAILS")
    print("="*80)
    print("Features:")
    print("- Transaktionsart-Kategorisierung")
    print("- Valuta-Datum Extraktion")
    print("- WKN/ISIN Erkennung")
    print("- Verwendung von qwen3:8b (schnell) oder qwen3:30b (genauer)")
    print("- Deutsches Zahlenformat korrekt verarbeitet\n")
    
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} Kontoauszüge für V4 Analyse\n")
    
    all_analyses = []
    erfolgreiche = 0
    
    for i, json_file in enumerate(json_files, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(json_files)}] Verarbeite: {json_file.name}")
        print(f"{'='*70}")
        
        analysis = ask_llm_detailed_analysis_v4(str(json_file))
        all_analyses.append(analysis)
        
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            # Detaillierte Ausgabe
            konto = analysis.get('kontodaten', {})
            print(f"\n📊 KONTODATEN:")
            print(f"   Inhaber: {konto.get('kontoinhaber', 'N/A')}")
            print(f"   Nummer: {konto.get('kontonummer', 'N/A')}")
            print(f"   Bank: {konto.get('bank', 'N/A')}")
            
            # Zeitraum und Salden
            zeitraum = analysis.get('zeitraum', {})
            print(f"\n📅 ZEITRAUM: {zeitraum.get('von', 'N/A')} - {zeitraum.get('bis', 'N/A')}")
            
            anfang = analysis.get('anfangssaldo', {})
            ende = analysis.get('endsaldo', {})
            print(f"\n💰 SALDEN:")
            print(f"   Start: {anfang.get('betrag_original', anfang.get('betrag', 'N/A'))}")
            print(f"   Ende:  {ende.get('betrag_original', ende.get('betrag', 'N/A'))}")
            
            # Transaktionen mit Details
            trans = analysis.get('transaktionen', [])
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} erfasst")
            
            if trans and len(trans) <= 5:
                for t in trans[:3]:
                    print(f"\n   #{t.get('nr', '?')} {t.get('buchungsdatum', 'N/A')}:")
                    print(f"      Art: {t.get('art', 'N/A')}")
                    print(f"      Betrag: {t.get('betrag_original', t.get('betrag', 'N/A'))}")
                    if t.get('valuta'):
                        print(f"      Valuta: {t['valuta']}")
                    if t.get('wertpapier'):
                        wp = t['wertpapier']
                        print(f"      Wertpapier: {wp.get('name', 'N/A')} (WKN: {wp.get('wkn', 'N/A')})")
            
            # Transaktionsarten-Übersicht
            uebersicht = analysis.get('transaktionsarten_uebersicht', {})
            if uebersicht:
                print(f"\n📊 TRANSAKTIONSARTEN:")
                for art, anzahl in uebersicht.items():
                    if anzahl > 0:
                        print(f"   {art}: {anzahl}x")
            
            # Validierung
            val = analysis.get('validierung', analysis.get('zusammenfassung', {}))
            if val.get('saldo_korrekt'):
                print(f"\n✅ SALDENPRÜFUNG: ERFOLGREICH")
                erfolgreiche += 1
            else:
                diff = val.get('differenz', 'N/A')
                print(f"\n⚠️ SALDENPRÜFUNG: Differenz {diff} EUR")
    
    # Speichern
    output_file = "kontoauszuege_analyse_komplett_v4.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "4.0",
            "beschreibung": "Erweiterte Analyse mit Transaktionskategorisierung, Valuta-Extraktion und qwen3:30b",
            "model": "qwen3:8b",
            "features": [
                "Transaktionsart-Klassifizierung",
                "Valuta-Datum Extraktion",
                "WKN/ISIN Erkennung",
                "Deutsches Zahlenformat",
                "Erweiterte Kontodaten"
            ],
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "erfolgreiche_pruefungen": erfolgreiche
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print(f"✅ ANALYSE V4 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche}/{len(json_files)}")
    print(f"🤖 Verwendet: qwen3:8b für diese Analyse")
    print("="*80)


if __name__ == "__main__":
    # Prüfe Ollama
    try:
        client = ollama.Client(host="https://fs.aiora.rest")
        print("Teste Ollama Verbindung...")
        client.list()
        print("✓ Ollama verfügbar")
        print("✓ Verwende qwen3:8b für schnelle Ergebnisse\n")
    except Exception as e:
        print(f"⚠️  Ollama nicht erreichbar: {e}")
        sys.exit(1)
    
    # V4 Analyse
    analyze_all_kontoauszuege_v4()