from flask import Flask, request, jsonify
import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span

app = Flask(__name__)

# Load the spaCy model
nlp = spacy.load("en_core_web_md")
# Create a custom matchers
matcher = Matcher(nlp.vocab)
website_pattern = [{"LIKE_URL": True}]
matcher.add("WEBSITE", [website_pattern])
email_pattern = [{"LIKE_EMAIL": True}]
matcher.add("EMAIL", [email_pattern])
brand_pattern = [{"POS": "PROPN", "IS_TITLE": True}]
matcher.add("BRAND", [brand_pattern])

def redact_pii(text):
    doc = nlp(text)

    # Add custom website, email, and brand entities
    matches = matcher(doc)
    new_ents = []
    for match_id, start, end in matches:
        span = Span(doc, start, end, label=nlp.vocab.strings[match_id])
        new_ents.append(span)

    # Merge overlapping entities, prioritizing existing entities
    all_ents = list(doc.ents) + new_ents
    all_ents = sorted(all_ents, key=lambda e: e.start)
    merged_ents = []
    for ent in all_ents:
        if not merged_ents or ent.start >= merged_ents[-1].end:
            merged_ents.append(ent)
        elif ent.end > merged_ents[-1].end:
            merged_ents[-1] = Span(doc, merged_ents[-1].start, ent.end, label=merged_ents[-1].label_)

    doc.ents = merged_ents

    redacted_text = text
    for ent in reversed(doc.ents):
        if ent.label_ in ["PERSON", "ORG", "GPE", "MONEY", "LOC", "PRODUCT", "DATE", "TIME", "FAC", "LAW", "EVENT", "NORP", "WEBSITE", "EMAIL", "WORK_OF_ART", "BRAND"]:
            redacted_text = redacted_text[:ent.start_char] + "[REDACTED]" + redacted_text[ent.end_char:]

    return redacted_text

@app.route('/redact', methods=['POST'])
def redact():
    data = request.json
    if 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400

    text = data['text']
    redacted_text = redact_pii(text)

    return jsonify({'redacted_text': redacted_text})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
