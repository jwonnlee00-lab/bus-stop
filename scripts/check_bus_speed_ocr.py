"""Compare a visual transcription to Windows OCR positions; OCR never edits data."""
import csv
import json
import re
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'data/sources/bus_speed_2025'
FIELDS = ['speed_morning','speed_midday','speed_evening','speed_average']


def main():
    with (D / 'transcribed_rows.tsv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f,delimiter='\t'))
    comparisons, discrepancies = [], []
    for page in [338,339,340]:
        ocr = json.loads((D / f'ocr_{page}.json').read_text(encoding='utf-8-sig'))
        labels = sorted([line for line in ocr if line['words'] and
                         275 <= line['words'][0]['x'] < 680 and 340 < line['words'][0]['y'] < 1850],
                        key=lambda line:line['words'][0]['y'])
        selected = [r for r in rows if int(r['pdf_page']) == page]
        assert len(labels) == len(selected)
        for row, label in zip(selected,labels):
            y = label['words'][0]['y']
            issues = []
            for field,(left,right) in zip(FIELDS,[(680,835),(835,995),(995,1155),(1155,1300)]):
                words = sorted([w for line in ocr for w in line['words']
                                if left <= w['x'] < right and abs(w['y']-y)<13],key=lambda w:w['x'])
                text = ''.join(w['text'] for w in words)
                digits = re.sub(r'\D','',text)
                expected = row[field].replace('.','')
                status = 'ocr_digits_agree' if digits == expected else 'visual_review_required'
                comparisons.append(dict(page=page,route_no=row['route_no'],field=field,
                                        expected=row[field],ocr=text,status=status))
                if status != 'ocr_digits_agree':
                    issues.append(field)
            if issues:
                discrepancies.append(dict(page=page, route_no=row['route_no'],y=y,fields=issues))
    # Put full source rows beside their expected numbers for review of OCR disagreements.
    for page in [338,339,340]:
        subset = [r for r in discrepancies if r['page']==page]
        sheet = Image.new('RGB',(1330,85*len(subset)), 'white')
        draw = ImageDraw.Draw(sheet)
        source = Image.open(D / f'pdf_{page}.png')
        for i,item in enumerate(subset):
            row = next(r for r in rows if r['route_no']==item['route_no'])
            draw.text((8,i*85), f"row {item['route_no']}: "+' | '.join(row[f] for f in FIELDS),fill='black')
            sheet.paste(source.crop((275,item['y']-7,1300,item['y']+33)).resize((1281,50)),(8,i*85+20))
        if subset:
            sheet.save(D / f'ocr_disagreements_{page}.png')
    result = dict(counts=dict(Counter(c['status'] for c in comparisons)), comparisons=comparisons,
                  note='Disagreements are queued for visual source review, not corrected from OCR.')
    (D / 'ocr_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(counts=result['counts'],review_rows=discrepancies),ensure_ascii=False))


if __name__ == '__main__':
    main()
