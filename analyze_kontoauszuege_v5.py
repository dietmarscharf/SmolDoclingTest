#!/usr/bin/env python3
"""
Version 5: Korrekte Extraktion von Anfangs- und Endsaldo direkt aus dem Dokument
- Endsaldo wird NICHT berechnet, sondern extrahiert
- Nur echte Transaktionen zwischen den Salden werden erfasst
- Hinweise und Fußnoten werden ignoriert
"""

import json
import sys
import re
from pathlib import Path
import ollama
from typing import Dict, Any, List, Optional, Tuple
import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_german_amount(amount_str: str) -> Decimal:
    """Konvertiert deutschen Betrag zu Decimal"""
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
    
    if 'wertpapier' in desc_lower or 'wertp.' in desc_lower:
        return 'Wertpapierkauf' if betrag < 0 else 'Wertpapierverkauf'
    elif 'überweisung' in desc_lower or 'übertrag' in desc_lower:
        return 'Überweisung ausgehend' if betrag < 0 else 'Überweisung eingehend'
    elif 'gutschrift' in desc_lower:
        return 'Gutschrift'
    elif 'lastschr' in desc_lower or 'depotentgelt' in desc_lower:
        return 'Lastschrift'
    elif 'entgelt' in desc_lower or 'gebühr' in desc_lower:
        return 'Gebühren'
    elif 'abrechnung' in desc_lower:
        return 'Verwahrentgelt' if 'verwahrentgelt' in desc_lower else 'Abrechnung'
    elif 'zins' in desc_lower:
        return 'Zinsen'
    elif betrag > 0:
        return 'Eingang'
    else:
        return 'Ausgang'


def extract_wkn_isin(description: str) -> Tuple[Optional[str], Optional[str]]:
    """Extrahiert WKN und ISIN aus Beschreibung"""
    wkn = None
    isin = None
    
    wkn_match = re.search(r'WKN\s+([A-Z0-9]{6})', description)
    if wkn_match:
        wkn = wkn_match.group(1)
    
    isin_match = re.search(r'([A-Z]{2}[A-Z0-9]{10})', description)
    if isin_match:
        isin = isin_match.group(1)
    
    return wkn, isin


def ask_llm_v5_analysis(json_file: str, 
                        ollama_url: str = "https://fs.aiora.rest",
                        model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 5: Korrekte Salden-Extraktion und Transaktions-Identifizierung
    """
    logger.info(f"Analysiere V5 (korrekte Salden): {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse
    doc_text = content.get("text", "")[:20000]
    
    # Sehr explizite Anweisungen für V5
    question = """EXTREM WICHTIG - KORREKTE SALDEN-EXTRAKTION:

DEUTSCHES ZAHLENFORMAT:
- "405.107,75" bedeutet 405107.75 (vierhunderttausendeinhundertsieben)
- "450.105,96" bedeutet 450105.96 (vierhundertfünfzigtausendeinhundertfünf)
- Punkt = Tausender (entfernen!), Komma = Dezimal (zu Punkt!)

KRITISCHE REGELN FÜR KONTOAUSZÜGE:

1. ANFANGSSALDO:
   - Suche: "Kontostand am [DATUM], Auszug Nr. [X]"
   - Dies ist der ERSTE Kontostand VOR den Transaktionen
   - Beispiel: "Kontostand am 29.04.2022, Auszug Nr. 3 405.107,75"
   - Dies ist NICHT eine Transaktion!

2. ENDSALDO: 
   - Suche: "Kontostand am [DATUM] um [UHRZEIT] Uhr" oder "Kontostand am [DATUM]"
   - Dies ist der LETZTE Kontostand NACH den Transaktionen
   - Beispiel: "Kontostand am 31.05.2022 um 20:03 Uhr 450.105,96"
   - Dies ist NICHT eine Transaktion!
   - MUSS aus dem Dokument extrahiert werden, NICHT berechnet!

3. NUR ECHTE TRANSAKTIONEN (zwischen Anfangs- und Endsaldo):
   - Hat ein DATUM (z.B. 02.05.2022)
   - Hat einen BETRAG mit + oder -
   - Ist KEINE Überschrift, Fußnote oder Hinweis
   - IGNORIERE: "Hinweise zum Kontoauszug", "Rechnungsabschlüsse gelten als genehmigt", etc.

BEISPIEL KORREKTE EXTRAKTION für Auszug 4/2022:
- Anfangssaldo: 405.107,75 (29.04.2022)
- Transaktion 1: 02.05.2022: -1,95 (Entgelt)
- Transaktion 2: 16.05.2022: -23.700,00 (Überweisung)
- Transaktion 3: 16.05.2022: +68.700,16 (Gutschrift)
- Endsaldo: 450.105,96 (31.05.2022)
- Prüfung: 405107.75 + (-1.95 - 23700 + 68700.16) = 450105.96 ✓

WICHTIG: Extrahiere Anfangs- und Endsaldo DIREKT aus dem Text, berechne sie NICHT!"""
    
    prompt = f"""Du bist ein präziser deutscher Bankprüfer. Analysiere diesen Kontoauszug EXAKT:

{doc_text}

{question}

Antworte im JSON Format:
{{
    "datei": "{Path(json_file).name}",
    "auszug_nummer": "extrahiere aus 'Auszug Nr. X'",
    "kontodaten": {{
        "kontonummer": "21503990 oder andere",
        "kontoinhaber": "BLUEITS GmbH oder andere",
        "bank": "Sparkasse Amberg-Sulzbach",
        "kontoart": "Geldmarktkonto"
    }},
    "anfangssaldo": {{
        "betrag": 405107.75,  // Beispiel - KEIN Tausenderpunkt!
        "betrag_text": "405.107,75 EUR",  // Original mit deutschem Format
        "datum": "29.04.2022",
        "beschreibung": "Kontostand am 29.04.2022, Auszug Nr. 3"
    }},
    "endsaldo": {{
        "betrag": 450105.96,  // DIREKT AUS DOKUMENT, NICHT BERECHNET!
        "betrag_text": "450.105,96 EUR",
        "datum": "31.05.2022",
        "uhrzeit": "20:03",
        "beschreibung": "Kontostand am 31.05.2022 um 20:03 Uhr"
    }},
    "transaktionen": [
        {{
            "nr": 1,
            "buchungsdatum": "02.05.2022",
            "valuta": "30.04.2022",
            "art": "Gebühren",
            "beschreibung": "Entgeltabrechnung / Wert: 30.04.2022",
            "betrag": -1.95,
            "betrag_text": "-1,95"
        }},
        {{
            "nr": 2,
            "buchungsdatum": "16.05.2022",
            "valuta": null,
            "art": "Überweisung ausgehend",
            "beschreibung": "Überweisung/Übertrag BLUEITS GmbH Kontoübertrag",
            "betrag": -23700.00,
            "betrag_text": "-23.700,00"
        }},
        {{
            "nr": 3,
            "buchungsdatum": "16.05.2022",
            "valuta": null,
            "art": "Gutschrift",
            "beschreibung": "Gutschriftseingang DURCHLFD.SPERRBETRAEGE...",
            "betrag": 68700.16,
            "betrag_text": "68.700,16",
            "wertpapier": {{"wkn": "A1CX3T"}}
        }}
    ],
    "anzahl_transaktionen": 3,  // NUR echte Transaktionen!
    "transaktionen_summe": 44998.21,
    "saldenprüfung": {{
        "anfangssaldo": 405107.75,
        "plus_transaktionen": 44998.21,
        "ergibt_endsaldo": 450105.96,
        "dokument_endsaldo": 450105.96,  // Aus Dokument extrahiert!
        "differenz": 0.00,
        "prüfung_ok": true
    }},
    "transaktionsarten_übersicht": {{
        "Gebühren": 1,
        "Überweisung ausgehend": 1,
        "Gutschrift": 1
    }},
    "wertpapiere": ["A1CX3T"]
}}

KRITISCH: 
- Endsaldo MUSS aus "Kontostand am..." am Ende extrahiert werden
- NICHT aus Transaktionen berechnen!
- NUR echte Transaktionen mit Datum und Betrag zählen"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende V5 Anfrage mit korrekter Salden-Logik...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """Du bist ein deutscher Bankprüfer. WICHTIGSTE REGELN:
1. Anfangssaldo = "Kontostand am [Datum], Auszug Nr. X" VOR Transaktionen
2. Endsaldo = "Kontostand am [Datum]" NACH Transaktionen (NICHT berechnen!)
3. NUR Buchungen mit Datum zwischen diesen Salden sind Transaktionen
4. Deutsche Zahlen: 405.107,75 = 405107.75 für JSON
5. Prüfung: Anfang + Transaktionen = Ende (muss stimmen!)"""
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
                "num_predict": 8192
            }
        )
        
        if response and 'message' in response:
            try:
                result = json.loads(response['message']['content'])
                
                # Nachbearbeitung
                if 'transaktionen' in result:
                    for trans in result['transaktionen']:
                        # Valuta extrahieren
                        if not trans.get('valuta') and 'beschreibung' in trans:
                            trans['valuta'] = extract_valuta_date(trans['beschreibung'])
                        
                        # Transaktionsart verfeinern
                        if 'beschreibung' in trans and 'betrag' in trans:
                            betrag = Decimal(str(trans['betrag']))
                            if 'art' not in trans or trans['art'] == 'Unbekannt':
                                trans['art'] = classify_transaction_type(trans['beschreibung'], betrag)
                        
                        # WKN/ISIN
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
                    
                    result['python_validierung'] = {
                        'anfangssaldo': float(anfang),
                        'endsaldo_aus_dokument': float(ende),
                        'transaktionen_summe': float(trans_summe),
                        'berechneter_endsaldo': float(berechnet),
                        'differenz': float(differenz),
                        'validierung_ok': abs(differenz) < Decimal('0.01'),
                        'hinweis': 'Endsaldo wurde aus Dokument extrahiert, nicht berechnet'
                    }
                    
                    if abs(differenz) < Decimal('0.01'):
                        logger.info("✅ V5 Saldenprüfung erfolgreich!")
                    else:
                        logger.warning(f"⚠️ V5 Saldendifferenz: {differenz:.2f} EUR")
                        
                except Exception as e:
                    result['python_validierung'] = {'fehler': str(e)}
                
                logger.info("✓ V5 Analyse abgeschlossen")
                return result
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON Parsing fehlgeschlagen: {e}")
                return {"datei": Path(json_file).name, "fehler": "JSON Parsing Error"}
    
    except Exception as e:
        logger.error(f"Fehler bei LLM Anfrage: {e}")
        return {"datei": Path(json_file).name, "fehler": str(e)}


def analyze_all_kontoauszuege_v5():
    """
    Version 5: Mit korrekter Salden-Extraktion
    """
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V5 - KORREKTE SALDEN-EXTRAKTION")
    print("="*80)
    print("Verbesserungen:")
    print("✓ Endsaldo wird aus Dokument extrahiert, nicht berechnet")
    print("✓ Nur echte Transaktionen zwischen Salden werden erfasst")
    print("✓ Hinweise und Fußnoten werden ignoriert")
    print("✓ Deutsches Zahlenformat korrekt verarbeitet\n")
    
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} Kontoauszüge für V5 Analyse\n")
    
    all_analyses = []
    erfolgreiche = 0
    
    for i, json_file in enumerate(json_files, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(json_files)}] Verarbeite: {json_file.name}")
        print(f"{'='*70}")
        
        analysis = ask_llm_v5_analysis(str(json_file))
        all_analyses.append(analysis)
        
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            # Ausgabe
            print(f"\n📊 AUSZUG {analysis.get('auszug_nummer', '?')}/2022")
            
            konto = analysis.get('kontodaten', {})
            print(f"   Konto: {konto.get('kontonummer', 'N/A')} ({konto.get('kontoinhaber', 'N/A')})")
            
            # Salden
            anfang = analysis.get('anfangssaldo', {})
            ende = analysis.get('endsaldo', {})
            print(f"\n💰 SALDEN (aus Dokument extrahiert):")
            print(f"   Anfang: {anfang.get('betrag_text', 'N/A')} ({anfang.get('datum', 'N/A')})")
            print(f"   Ende:   {ende.get('betrag_text', 'N/A')} ({ende.get('datum', 'N/A')})")
            
            # Transaktionen
            trans = analysis.get('transaktionen', [])
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} Stück")
            
            if trans and len(trans) <= 5:
                for t in trans:
                    print(f"   {t.get('buchungsdatum', 'N/A')}: {t.get('betrag_text', t.get('betrag', 'N/A'))} - {t.get('art', 'N/A')}")
            elif trans:
                for t in trans[:3]:
                    print(f"   {t.get('buchungsdatum', 'N/A')}: {t.get('betrag_text', t.get('betrag', 'N/A'))} - {t.get('art', 'N/A')}")
                print(f"   ... und {len(trans)-3} weitere")
            
            # Validierung
            val = analysis.get('python_validierung', {})
            if val.get('validierung_ok'):
                print(f"\n✅ SALDENPRÜFUNG ERFOLGREICH:")
                print(f"   {val.get('anfangssaldo', 0):.2f} + {val.get('transaktionen_summe', 0):.2f} = {val.get('berechneter_endsaldo', 0):.2f}")
                print(f"   Dokument-Endsaldo: {val.get('endsaldo_aus_dokument', 0):.2f} ✓")
                erfolgreiche += 1
            else:
                diff = val.get('differenz', 'N/A')
                print(f"\n⚠️ SALDENPRÜFUNG - Differenz: {diff:.2f} EUR")
                print(f"   Berechnet: {val.get('berechneter_endsaldo', 0):.2f}")
                print(f"   Dokument:  {val.get('endsaldo_aus_dokument', 0):.2f}")
    
    # Speichern
    output_file = "kontoauszuege_analyse_komplett_v5.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "5.0",
            "beschreibung": "Korrekte Salden-Extraktion - Endsaldo aus Dokument, nicht berechnet",
            "model": "qwen3:8b",
            "verbesserungen": [
                "Endsaldo direkt aus Dokument extrahiert",
                "Nur echte Transaktionen gezählt",
                "Hinweise/Fußnoten ignoriert",
                "Anfangs-/Endsaldo sind keine Transaktionen"
            ],
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "erfolgreiche_pruefungen": erfolgreiche
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print(f"✅ ANALYSE V5 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche}/{len(json_files)}")
    print("="*80)


if __name__ == "__main__":
    # Prüfe Ollama
    try:
        client = ollama.Client(host="https://fs.aiora.rest")
        print("Teste Ollama Verbindung...")
        client.list()
        print("✓ Ollama verfügbar\n")
    except Exception as e:
        print(f"⚠️  Ollama nicht erreichbar: {e}")
        sys.exit(1)
    
    # V5 Analyse
    analyze_all_kontoauszuege_v5()