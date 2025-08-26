#!/usr/bin/env python3
"""
Version 3: Korrigierte Analyse mit europäischem Zahlenformat
Berücksichtigt deutsches Format: 1.234,56 EUR (Punkt als Tausender, Komma als Dezimal)
"""

import json
import sys
import re
from pathlib import Path
import ollama
from typing import Dict, Any, List
import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_german_amount(amount_str: str) -> Decimal:
    """
    Konvertiert deutschen Betrag zu Decimal
    Beispiele: 
    "1.234,56" -> 1234.56
    "-1.234,56" -> -1234.56
    "391.214,64" -> 391214.64
    """
    if isinstance(amount_str, (int, float)):
        return Decimal(str(amount_str))
        
    # String bereinigen
    amount_str = str(amount_str).replace('EUR', '').strip()
    
    # Deutsche Formatierung: Punkt als Tausender entfernen, Komma durch Punkt ersetzen
    amount_str = amount_str.replace('.', '').replace(',', '.')
    
    try:
        return Decimal(amount_str)
    except:
        logger.warning(f"Konnte Betrag nicht parsen: {amount_str}")
        return Decimal('0')


def ask_llm_detailed_analysis_v3(json_file: str, 
                                 ollama_url: str = "https://fs.aiora.rest",
                                 model: str = "qwen3:8b") -> Dict[str, Any]:
    """
    Version 3: Detaillierte Analyse mit korrektem deutschen Zahlenformat
    """
    logger.info(f"Analysiere V3 (deutsches Format): {json_file}")
    
    # JSON laden
    with open(json_file, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    # Text für Analyse vorbereiten
    doc_text = content.get("text", "")[:15000]
    
    # Sehr explizite Anweisungen für deutsches Zahlenformat
    question = """EXTREM WICHTIG - DEUTSCHES ZAHLENFORMAT:
    
Diese Dokumente verwenden DEUTSCHES/EUROPÄISCHES Zahlenformat:
- PUNKT (.) = Tausendertrennzeichen (IGNORIEREN!)
- KOMMA (,) = Dezimaltrennzeichen
- Beispiele:
  * "391.214,64" bedeutet 391214.64 (dreihunderteinundneunzigtausend)
  * "1.234,56" bedeutet 1234.56 (eintausendzweihundertvierunddreißig)
  * "-101.046,00" bedeutet -101046.00 (minus einhunderteintausend)

AUFGABE: Extrahiere ALLE Transaktionen aus diesem deutschen Kontoauszug:

1. ANFANGSSALDO: Der ERSTE "Kontostand am" Eintrag (z.B. "Kontostand am 31.03.2022")
2. ENDSALDO: Der LETZTE "Kontostand am" Eintrag (z.B. "Kontostand am 29.04.2022")
3. ALLE TRANSAKTIONEN dazwischen mit:
   - Datum (TT.MM.JJJJ)
   - Vollständige Beschreibung
   - Betrag in DEZIMALFORMAT (ohne Tausenderpunkte!)
   
4. SALDENPRÜFUNG: 
   Anfangssaldo + Summe(Transaktionen) = Endsaldo?

WICHTIG: Konvertiere alle Beträge zu reinen Zahlen OHNE Tausenderpunkte!
- "391.214,64" → 391214.64
- "37.000,00" → 37000.00
- "-101.046,00" → -101046.00"""
    
    prompt = f"""Du bist ein deutscher Finanzprüfer. Analysiere diesen DEUTSCHEN Kontoauszug mit DEUTSCHEM Zahlenformat:

{doc_text}

{question}

Antworte im JSON Format mit DEZIMALZAHLEN (amerikanisches Format für JSON):
{{
    "datei": "{Path(json_file).name}",
    "kontonummer": "21503990 oder andere gefundene Nummer",
    "zeitraum": "TT.MM.JJJJ bis TT.MM.JJJJ",
    "anfangssaldo": {{
        "betrag": 391214.64,  // KEIN Tausenderpunkt, Punkt als Dezimal!
        "betrag_text": "391.214,64 EUR",  // Original deutsches Format
        "datum": "31.03.2022",
        "beschreibung": "Kontostand am..."
    }},
    "endsaldo": {{
        "betrag": 405107.75,  // KEIN Tausenderpunkt!
        "betrag_text": "405.107,75 EUR",  // Original
        "datum": "29.04.2022",
        "beschreibung": "Kontostand am..."
    }},
    "transaktionen": [
        {{
            "datum": "01.04.2022",
            "beschreibung": "Vollständiger Text",
            "betrag": -170.86,  // Dezimalzahl ohne Tausenderpunkt!
            "betrag_text": "-170,86 EUR",  // Original
            "typ": "Belastung"
        }}
    ],
    "transaktionen_summe": 13893.11,  // Summe als Dezimalzahl
    "berechneter_endsaldo": 405107.75,
    "saldo_korrekt": true,
    "saldo_differenz": 0.00,
    "anzahl_transaktionen": 11,
    "wertpapiere": ["TESLA INC. (WKN A1CX3T)"],
    "pruefung": "OK - Alle Transaktionen erfasst"
}}

KRITISCH: Wandle ALLE deutschen Zahlen (1.234,56) in JSON-Zahlen (1234.56) um!"""
    
    try:
        client = ollama.Client(host=ollama_url)
        
        logger.info(f"Sende V3 Anfrage mit deutschem Format an Ollama...")
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """Du bist ein deutscher Buchhalter. WICHTIG:
- Deutsche Dokumente haben: PUNKT als Tausendertrennzeichen, KOMMA als Dezimaltrennzeichen
- Beispiel deutsch: 391.214,64 EUR = dreihunderteinundneunzigtausend Euro
- Für JSON ausgeben als: 391214.64 (amerikanisches Format)
- IMMER Tausenderpunkte entfernen und Komma durch Punkt ersetzen für JSON!"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={
                "temperature": 0.01,  # Minimale Temperatur für Präzision
                "top_p": 1.0,
                "num_predict": 8192  # Mehr Token für vollständige Erfassung
            }
        )
        
        if response and 'message' in response:
            try:
                result = json.loads(response['message']['content'])
                
                # Python-Validierung mit deutschem Format
                try:
                    # Parse mit deutschem Format falls nötig
                    anfang_betrag = result['anfangssaldo'].get('betrag', 0)
                    if isinstance(anfang_betrag, str):
                        anfang = parse_german_amount(anfang_betrag)
                    else:
                        anfang = Decimal(str(anfang_betrag))
                    
                    ende_betrag = result['endsaldo'].get('betrag', 0)
                    if isinstance(ende_betrag, str):
                        ende = parse_german_amount(ende_betrag)
                    else:
                        ende = Decimal(str(ende_betrag))
                    
                    # Transaktionen summieren
                    trans_summe = Decimal('0')
                    for trans in result.get('transaktionen', []):
                        betrag = trans.get('betrag', 0)
                        if isinstance(betrag, str):
                            trans_summe += parse_german_amount(betrag)
                        else:
                            trans_summe += Decimal(str(betrag))
                    
                    berechnet = anfang + trans_summe
                    differenz = ende - berechnet
                    
                    result['python_validierung'] = {
                        'anfangssaldo': float(anfang),
                        'transaktionen_summe': float(trans_summe),
                        'berechneter_endsaldo': float(berechnet),
                        'tatsaechlicher_endsaldo': float(ende),
                        'differenz': float(differenz),
                        'validierung_ok': abs(differenz) < Decimal('0.01'),
                        'format_hinweis': 'Deutsches Format korrekt verarbeitet'
                    }
                    
                    if abs(differenz) < Decimal('0.01'):
                        logger.info("✅ Saldenprüfung erfolgreich!")
                    else:
                        logger.warning(f"⚠️ Saldendifferenz: {differenz}")
                        
                except Exception as e:
                    result['python_validierung'] = {'fehler': str(e)}
                
                logger.info("✓ V3 Analyse mit deutschem Format erfolgreich")
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


def analyze_all_kontoauszuege_v3():
    """
    Version 3: Mit korrektem deutschen Zahlenformat
    """
    print("\n" + "="*80)
    print("KONTOAUSZUG ANALYSE V3 - MIT DEUTSCHEM ZAHLENFORMAT")
    print("="*80)
    print("Berücksichtigt: 1.234,56 EUR Format (Punkt=Tausender, Komma=Dezimal)\n")
    
    # Finde alle Kontoauszug JSON Dateien
    json_files = sorted(Path(".").glob("Konto_Auszug_2022_*_result.json"))
    
    if not json_files:
        print("❌ Keine Kontoauszug JSON Dateien gefunden!")
        return
    
    print(f"Gefunden: {len(json_files)} deutsche Kontoauszüge\n")
    
    all_analyses = []
    erfolgreiche_pruefungen = 0
    
    for i, json_file in enumerate(json_files, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(json_files)}] Analysiere: {json_file.name}")
        print(f"{'='*60}")
        
        analysis = ask_llm_detailed_analysis_v3(str(json_file))
        all_analyses.append(analysis)
        
        if "fehler" in analysis:
            print(f"❌ Fehler: {analysis['fehler']}")
        else:
            print(f"\n📊 {analysis.get('datei', json_file.name)}")
            print(f"   Konto: {analysis.get('kontonummer', 'N/A')}")
            print(f"   Zeitraum: {analysis.get('zeitraum', 'N/A')}")
            
            # Salden mit Original-Format
            anfang = analysis.get('anfangssaldo', {})
            ende = analysis.get('endsaldo', {})
            print(f"\n💰 SALDEN:")
            print(f"   Start: {anfang.get('betrag_text', anfang.get('betrag', 'N/A'))} ({anfang.get('datum', '')})")
            print(f"   Ende:  {ende.get('betrag_text', ende.get('betrag', 'N/A'))} ({ende.get('datum', '')})")
            
            # Transaktionen
            trans = analysis.get('transaktionen', [])
            print(f"\n📝 {len(trans)} Transaktionen erfasst")
            
            # Validierung
            val = analysis.get('python_validierung', {})
            if val.get('validierung_ok'):
                print(f"\n✅ SALDO PRÜFUNG: ERFOLGREICH")
                print(f"   {val.get('anfangssaldo', 0):.2f} + {val.get('transaktionen_summe', 0):.2f} = {val.get('berechneter_endsaldo', 0):.2f}")
                erfolgreiche_pruefungen += 1
            else:
                diff = val.get('differenz', analysis.get('saldo_differenz', 'N/A'))
                print(f"\n⚠️ SALDO PRÜFUNG: Differenz {diff:.2f} EUR")
                print(f"   Erwartet: {val.get('tatsaechlicher_endsaldo', 0):.2f}")
                print(f"   Berechnet: {val.get('berechneter_endsaldo', 0):.2f}")
    
    # Speichern
    output_file = "kontoauszuege_analyse_komplett_v3.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "3.0",
            "beschreibung": "Analyse mit korrektem deutschen Zahlenformat (1.234,56 EUR)",
            "analysen": all_analyses,
            "anzahl_dokumente": len(all_analyses),
            "erfolgreiche_pruefungen": erfolgreiche_pruefungen,
            "format": "Deutsches Format korrekt verarbeitet"
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print(f"✅ ANALYSE V3 ABGESCHLOSSEN!")
    print(f"📊 Gespeichert in: {output_file}")
    print(f"✅ Erfolgreiche Saldenprüfungen: {erfolgreiche_pruefungen}/{len(json_files)}")
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
    
    # V3 Analyse mit deutschem Format
    analyze_all_kontoauszuege_v3()