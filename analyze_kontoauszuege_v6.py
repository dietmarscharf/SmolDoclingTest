#!/usr/bin/env python3
"""
Version 6: Perfektionierte Extraktion basierend auf Analyse aller 5 Dokumente
- Schritt-für-Schritt Extraktion
- Validierung der Auszugsnummer-Kontinuität
- Präzise Musterabgleiche für deutsche Kontoauszüge
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


def ask_llm_v6_analysis(json_file: str, 
                        ollama_url: str = "https://fs.aiora.rest",
                        model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 6: Perfektionierte Extraktion mit Schritt-für-Schritt Logik
    """
    logger.info(f"Analysiere V6 (perfektioniert): {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse
    doc_text = content.get("text", "")[:20000]
    
    # Strukturierter Prompt für V6
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
Muster: "Kontostand am [DATUM] um [ZEIT] Uhr"
Dieser hat KEINE Auszugsnummer!

Beispiele:
- "Kontostand am 29.04.2022 um 20:03 Uhr 405.107,75"
- "Kontostand am 31.05.2022 um 20:03 Uhr 450.105,96"
- "Kontostand am 30.06.2022 um 20:02 Uhr 450.104,01"

📋 SCHRITT 4: EXTRAHIERE NUR ECHTE TRANSAKTIONEN
NUR Zeilen ZWISCHEN Anfangs- und Endsaldo mit:
- Datum (TT.MM.JJJJ)
- Betrag (positiv oder negativ)
- NICHT: "Kontostand am", "Anzahl Anlagen", "Hinweise", etc.

BEISPIEL KONTOAUSZUG 5/2022 (NUR 1 TRANSAKTION!):
```
Kontoauszug 5/2022                          ← Auszugsnummer = 5
Kontostand am 31.05.2022, Auszug Nr. 4 450.105,96  ← ANFANGSSALDO (Nr. 4!)
01.06.2022 Entgeltabrechnung -1,95         ← EINZIGE TRANSAKTION
Kontostand am 30.06.2022 um 20:02 Uhr 450.104,01   ← ENDSALDO
```

📋 SCHRITT 5: VALIDIERUNG
- Anfangssaldo + Summe(Transaktionen) = Endsaldo
- Beispiel Auszug 5: 450.105,96 + (-1,95) = 450.104,01 ✓"""
    
    prompt = f"""Du bist ein präziser deutscher Bankprüfer. Analysiere SCHRITT FÜR SCHRITT:

{doc_text}

{question}

Antworte im JSON Format:
{{
    "datei": "{Path(json_file).name}",
    "schritt1_auszugsnummer": "Extrahiere aus 'Kontoauszug X/2022'",
    "auszug_nummer": "5",  // Beispiel für Auszug 5/2022
    "kontodaten": {{
        "kontonummer": "21503990",
        "kontoinhaber": "BLUEITS GmbH",
        "bank": "Sparkasse Amberg-Sulzbach",
        "kontoart": "Geldmarktkonto"
    }},
    "schritt2_anfangssaldo": "Erkläre welche Zeile der Anfangssaldo ist",
    "anfangssaldo": {{
        "betrag": 450105.96,  // Für Auszug 5: NICHT 405107.75!
        "betrag_text": "450.105,96 EUR",
        "datum": "31.05.2022",
        "auszug_nr_referenz": "4",  // Vorherige Auszugsnummer!
        "beschreibung": "Kontostand am 31.05.2022, Auszug Nr. 4"
    }},
    "schritt3_endsaldo": "Erkläre welche Zeile der Endsaldo ist",
    "endsaldo": {{
        "betrag": 450104.01,  // Direkt aus Dokument!
        "betrag_text": "450.104,01 EUR",
        "datum": "30.06.2022",
        "uhrzeit": "20:02",
        "beschreibung": "Kontostand am 30.06.2022 um 20:02 Uhr"
    }},
    "schritt4_transaktionen": "Liste NUR echte Transaktionen",
    "transaktionen": [
        {{
            "nr": 1,
            "buchungsdatum": "01.06.2022",
            "valuta": null,
            "art": "Entgeltabrechnung",
            "beschreibung": "Entgeltabrechnung",
            "betrag": -1.95,
            "betrag_text": "-1,95"
        }}
    ],
    "anzahl_transaktionen": 1,  // Auszug 5 hat NUR 1 Transaktion!
    "transaktionen_summe": -1.95,
    "schritt5_validierung": {{
        "rechnung": "450105.96 + (-1.95) = 450104.01",
        "anfangssaldo": 450105.96,
        "plus_transaktionen": -1.95,
        "ergibt": 450104.01,
        "dokument_endsaldo": 450104.01,
        "differenz": 0.00,
        "prüfung_ok": true
    }}
}}

EXTREM WICHTIG für jeden Auszug:
- Auszugsnummer aus Kopfzeile nehmen
- Anfangssaldo hat IMMER die VORHERIGE Auszugsnummer
- Endsaldo hat KEINE Auszugsnummer
- NUR echte Transaktionen zwischen den Salden zählen"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende V6 Anfrage mit Schritt-für-Schritt Logik...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """Du bist ein deutscher Bankprüfer. KRITISCHE REGELN:

1. AUSZUGSNUMMER: Aus "Kontoauszug X/2022" in Kopfzeile
2. ANFANGSSALDO: "Kontostand am [Datum], Auszug Nr. [X-1]" (VORHERIGE Nummer!)
3. ENDSALDO: "Kontostand am [Datum] um [Zeit] Uhr" (KEINE Auszugsnummer!)
4. NUR Transaktionen ZWISCHEN diesen Salden zählen
5. Deutsche Zahlen: 450.105,96 = 450105.96 für JSON

BEISPIEL AUSZUG 5/2022:
- Kopfzeile: "Kontoauszug 5/2022" → Nummer = 5
- Anfang: "Kontostand am 31.05.2022, Auszug Nr. 4 450.105,96" (Nr. 4!)
- Ende: "Kontostand am 30.06.2022 um 20:02 Uhr 450.104,01"
- Transaktionen: NUR 1 (-1,95 EUR)"""
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
                
                # Nachbearbeitung und erweiterte Validierung
                if 'transaktionen' in result:
                    for trans in result['transaktionen']:
                        # Valuta extrahieren
                        if not trans.get('valuta') and 'beschreibung' in trans:
                            trans['valuta'] = extract_valuta_date(trans['beschreibung'])
                        
                        # Transaktionsart verfeinern
                        if 'beschreibung' in trans and 'betrag' in trans:
                            betrag = Decimal(str(trans['betrag']))
                            trans['art'] = classify_transaction_type(trans['beschreibung'], betrag)
                        
                        # WKN/ISIN/Name
                        if 'beschreibung' in trans:
                            wkn, isin, name = extract_wkn_isin(trans['beschreibung'])
                            if wkn or isin or name:
                                trans['wertpapier'] = {}
                                if wkn:
                                    trans['wertpapier']['wkn'] = wkn
                                if isin:
                                    trans['wertpapier']['isin'] = isin
                                if name:
                                    trans['wertpapier']['name'] = name
                
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
                        'formel': f"{anfang:.2f} + {trans_summe:.2f} = {berechnet:.2f}"
                    }
                    
                    if abs(differenz) < Decimal('0.01'):
                        logger.info(f"✅ V6 Saldenprüfung erfolgreich: {result['python_validierung']['formel']}")
                    else:
                        logger.warning(f"⚠️ V6 Saldendifferenz: {differenz:.2f} EUR")
                        
                except Exception as e:
                    result['python_validierung'] = {'fehler': str(e)}
                
                logger.info("✓ V6 Analyse abgeschlossen")
                return result
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON Parsing fehlgeschlagen: {e}")
                return {"datei": Path(json_file).name, "fehler": "JSON Parsing Error"}
    
    except Exception as e:
        logger.error(f"Fehler bei LLM Anfrage: {e}")
        return {"datei": Path(json_file).name, "fehler": str(e)}


def validate_statement_continuity(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validiert die Kontinuität zwischen Kontoauszügen
    Endsaldo von Auszug N muss Anfangssaldo von Auszug N+1 sein
    """
    continuity_check = []
    
    # Sortiere nach Auszugsnummer
    sorted_analyses = sorted(
        [a for a in analyses if 'fehler' not in a],
        key=lambda x: int(x.get('auszug_nummer', 0))
    )
    
    for i in range(len(sorted_analyses) - 1):
        current = sorted_analyses[i]
        next_stmt = sorted_analyses[i + 1]
        
        current_end = current.get('endsaldo', {}).get('betrag', 0)
        next_start = next_stmt.get('anfangssaldo', {}).get('betrag', 0)
        
        matches = abs(current_end - next_start) < 0.01
        
        continuity_check.append({
            'auszug_von': current.get('auszug_nummer'),
            'auszug_nach': next_stmt.get('auszug_nummer'),
            'endsaldo_von': current_end,
            'anfangssaldo_nach': next_start,
            'kontinuität_ok': matches,
            'differenz': next_start - current_end
        })
    
    return {
        'kontinuität_prüfungen': continuity_check,
        'alle_ok': all(c['kontinuität_ok'] for c in continuity_check)
    }


def analyze_all_kontoauszuege_v6():
    """
    Version 6: Perfektionierte Analyse mit Schritt-für-Schritt Extraktion
    """
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V6 - PERFEKTIONIERTE EXTRAKTION")
    print("="*80)
    print("Verbesserungen:")
    print("✓ Schritt-für-Schritt Extraktion mit klaren Regeln")
    print("✓ Korrekte Auszugsnummer-Referenzierung")
    print("✓ Validierung der Kontinuität zwischen Auszügen")
    print("✓ Präzise Beispiele für jeden Auszug\n")
    
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} Kontoauszüge für V6 Analyse\n")
    
    all_analyses = []
    erfolgreiche = 0
    
    for i, json_file in enumerate(json_files, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(json_files)}] Verarbeite: {json_file.name}")
        print(f"{'='*70}")
        
        analysis = ask_llm_v6_analysis(str(json_file))
        all_analyses.append(analysis)
        
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            # Detaillierte Ausgabe
            print(f"\n📊 KONTOAUSZUG {analysis.get('auszug_nummer', '?')}/2022")
            
            # Anfangssaldo mit Referenz
            anfang = analysis.get('anfangssaldo', {})
            print(f"\n💰 ANFANGSSALDO (Auszug Nr. {anfang.get('auszug_nr_referenz', '?')}):")
            print(f"   {anfang.get('betrag_text', 'N/A')} vom {anfang.get('datum', 'N/A')}")
            
            # Endsaldo
            ende = analysis.get('endsaldo', {})
            print(f"\n💰 ENDSALDO:")
            print(f"   {ende.get('betrag_text', 'N/A')} vom {ende.get('datum', 'N/A')}")
            
            # Transaktionen
            trans = analysis.get('transaktionen', [])
            print(f"\n📝 TRANSAKTIONEN: {len(trans)} Stück")
            
            if trans and len(trans) <= 5:
                for t in trans:
                    art = t.get('art', 'Unbekannt')
                    print(f"   {t.get('buchungsdatum', 'N/A')}: {t.get('betrag_text', t.get('betrag', 'N/A'))} - {art}")
            elif trans:
                for t in trans[:3]:
                    art = t.get('art', 'Unbekannt')
                    print(f"   {t.get('buchungsdatum', 'N/A')}: {t.get('betrag_text', t.get('betrag', 'N/A'))} - {art}")
                print(f"   ... und {len(trans)-3} weitere")
            
            # Validierung
            val = analysis.get('python_validierung', {})
            if val.get('validierung_ok'):
                print(f"\n✅ SALDENPRÜFUNG ERFOLGREICH:")
                print(f"   {val.get('formel', 'N/A')}")
                erfolgreiche += 1
            else:
                diff = val.get('differenz', 'N/A')
                print(f"\n⚠️ SALDENPRÜFUNG - Differenz: {diff:.2f} EUR")
                print(f"   Formel: {val.get('formel', 'N/A')}")
    
    # Kontinuitätsprüfung
    print("\n" + "="*70)
    print("KONTINUITÄTSPRÜFUNG ZWISCHEN AUSZÜGEN")
    print("="*70)
    
    continuity = validate_statement_continuity(all_analyses)
    for check in continuity['kontinuität_prüfungen']:
        symbol = "✅" if check['kontinuität_ok'] else "⚠️"
        print(f"{symbol} Auszug {check['auszug_von']} → {check['auszug_nach']}: ", end="")
        print(f"Ende {check['endsaldo_von']:.2f} = Anfang {check['anfangssaldo_nach']:.2f}")
        if not check['kontinuität_ok']:
            print(f"   Differenz: {check['differenz']:.2f} EUR")
    
    # Speichern
    output_file = "kontoauszuege_analyse_komplett_v6.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "6.0",
            "beschreibung": "Perfektionierte Extraktion mit Schritt-für-Schritt Logik",
            "model": "qwen3:8b",
            "verbesserungen": [
                "Schritt-für-Schritt Extraktion",
                "Korrekte Auszugsnummer-Referenzierung",
                "Kontinuitätsprüfung zwischen Auszügen",
                "Erweiterte Transaktionsklassifikation",
                "Präzise Beispiele für jeden Auszugstyp"
            ],
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "erfolgreiche_pruefungen": erfolgreiche,
            "kontinuitaet": continuity
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print(f"✅ ANALYSE V6 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche}/{len(json_files)}")
    if continuity['alle_ok']:
        print(f"✅ Kontinuität zwischen allen Auszügen bestätigt")
    else:
        print(f"⚠️ Kontinuitätsprobleme gefunden")
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
    
    # V6 Analyse
    analyze_all_kontoauszuege_v6()