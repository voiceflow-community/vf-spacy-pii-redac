from flask import Flask, request, jsonify
import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Load the spaCy model
nlp = spacy.load(os.getenv('SPACY_MODEL', 'en_core_web_md'))

# Define all available matchers
AVAILABLE_MATCHERS = {
    "EMAIL": {
        "patterns": [[{"LIKE_EMAIL": True}]],
        "description": "Email addresses"
    },
    "WEBSITE": {
        "patterns": [[{"LIKE_URL": True}]],
        "description": "Website URLs"
    },
    "BRAND": {
        "patterns": [[{"POS": "PROPN", "IS_TITLE": True}]],
        "description": "Brand names"
    },
    "PHONE": {
        "patterns": [
            # Standard formats
            [{"SHAPE": "ddd-ddd-dddd"}],
            [{"SHAPE": "(ddd)ddd-dddd"}],
            [{"SHAPE": "dddddddddd"}],
            [{"SHAPE": "ddd.ddd.dddd"}],
            # International formats
            [{"TEXT": {"REGEX": "\\+\\d{1,3}[-\\s]?\\d{1,4}[-\\s]?\\d{4,10}"}}],  # With country code and optional separators
            [{"TEXT": {"REGEX": "\\+\\d{8,15}"}}],  # Plain international numbers
            # French formats
            [{"TEXT": {"REGEX": "\\+33\\d{9}"}}],   # French international
            [{"TEXT": {"REGEX": "0\\d{9}"}}],       # French national
            [{"TEXT": {"REGEX": "(\\+33|0)[-\\s]?[1-9]([-\\s]?\\d{2}){4}"}}],  # French with separators
        ],
        "description": "Phone numbers in various formats (international, local, with/without separators)"
    },
    "CREDIT_CARD": {
        "patterns": [[{"TEXT": {"REGEX": "\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}"}}]],
        "description": "Credit card numbers"
    },
    "SSN": {
        "patterns": [
            [{"SHAPE": "ddd-dd-dddd"}],
            [{"TEXT": {"REGEX": "\\d{3}-\\d{2}-\\d{4}"}}]
        ],
        "description": "Social Security Numbers"
    },
    "IP_ADDRESS": {
        "patterns": [[{"TEXT": {"REGEX": "\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b"}}]],
        "description": "IP addresses"
    },
    "ADDRESS": {
        "patterns": [
            # Postal/ZIP codes
            [{"SHAPE": "ddddd"}],  # French postal code
            [{"TEXT": {"REGEX": "\\b\\d{5}(-\\d{4})?\\b"}}],  # Generic postal code

            # Street numbers with street types
            [{"LIKE_NUM": True},
             {"LOWER": {"IN": ["rue", "avenue", "boulevard", "chemin", "impasse", "place", "route", "allée", "cours"]}},
             {"OP": "*"},  # Optional words in between
             {"OP": "*"}],

            # Street names (capturing the whole phrase)
            [{"LOWER": {"IN": ["rue", "avenue", "boulevard", "chemin", "impasse", "place", "route", "allée", "cours"]}},
             {"OP": "+"}, {"OP": "+"}, {"OP": "?"}],  # Multiple words following street type

            # Cities with postal codes
            [{"IS_ALPHA": True}, {"SHAPE": "ddddd"}],  # City name followed by postal code
            [{"SHAPE": "ddddd"}, {"IS_ALPHA": True}],  # Postal code followed by city name

            # Building/Apartment numbers with variations
            [{"LIKE_NUM": True},
             {"LOWER": {"IN": ["bis", "ter", "quater", "b", "t", "a"]}},
             {"OP": "?"}],

            # Common location words
            [{"LOWER": {"IN": ["résidence", "appartement", "appt", "apt", "bâtiment", "bat", "étage", "chez"]}},
             {"OP": "+"}, {"OP": "?"}],

            # Countries
            [{"ENT_TYPE": "GPE"}],  # Using SpaCy's built-in country/city detection
        ],
        "description": "Street addresses, postal codes, cities, and building numbers"
    },
    "ACCOUNT": {
        "patterns": [
            [{"TEXT": {"REGEX": "(?i)order[:#\\s-]*\\d+"}}],
            [{"TEXT": {"REGEX": "(?i)account[:#\\s-]*\\d+"}}],
            [{"TEXT": {"REGEX": "(?i)customer[:#\\s-]*\\d+"}}]
        ],
        "description": "Account/Order numbers"
    }
}

# Default NER entities to always include
DEFAULT_NER_ENTITIES = [
    "PERSON", "GPE", "DATE", "TIME", "NORP"
]

def setup_matcher(nlp, selected_matchers=None):
    """Initialize matcher with selected patterns"""
    matcher = Matcher(nlp.vocab)

    # If no matchers specified, use all available matchers
    if selected_matchers is None:
        selected_matchers = list(AVAILABLE_MATCHERS.keys())

    # Add selected patterns to matcher
    for matcher_name in selected_matchers:
        if matcher_name in AVAILABLE_MATCHERS:
            matcher.add(matcher_name, AVAILABLE_MATCHERS[matcher_name]["patterns"])

    return matcher

def redact_pii(text, selected_matchers=None):
    """Redact PII based on selected matchers"""
    # Setup matcher with selected patterns
    matcher = setup_matcher(nlp, selected_matchers)

    doc = nlp(text)

    # Add custom entities from matcher
    matches = matcher(doc)
    new_ents = []
    for match_id, start, end in matches:
        # Create span with more context if it's an address
        if nlp.vocab.strings[match_id] == "ADDRESS":
            # Try to extend the span to catch surrounding address components
            while start > 0 and (doc[start-1].text.lower() in ["in", "at", ",", "de", "du", "des", "le", "la", "les"] or
                               doc[start-1].like_num):
                start -= 1
            # Try to extend forward for additional address components
            while end < len(doc) and (doc[end].text in [",", ".", "-"] or
                                    doc[end].like_num or
                                    doc[end].text.lower() in ["street", "avenue", "road", "rue", "chemin"]):
                end += 1

        span = Span(doc, start, end, label=nlp.vocab.strings[match_id])
        new_ents.append(span)

    # Merge overlapping entities with smarter handling
    all_ents = list(doc.ents) + new_ents
    all_ents = sorted(all_ents, key=lambda e: (e.start, -e.end))  # Sort by start pos and prefer longer spans

    merged_ents = []
    current_span = None

    for ent in all_ents:
        if not current_span:
            current_span = ent
            continue

        # Check for overlap
        if ent.start <= current_span.end:
            # Merge spans if they overlap
            if ent.end > current_span.end:
                # Prefer ADDRESS label for merged spans containing address components
                if "ADDRESS" in [ent.label_, current_span.label_]:
                    label = "ADDRESS"
                else:
                    label = current_span.label_
                current_span = Span(doc, current_span.start, ent.end, label=label)
        else:
            merged_ents.append(current_span)
            current_span = ent

    if current_span:
        merged_ents.append(current_span)

    doc.ents = merged_ents

    # Redact entities
    redacted_text = text
    for ent in reversed(merged_ents):
        if ent.label_ in DEFAULT_NER_ENTITIES or ent.label_ in (selected_matchers or AVAILABLE_MATCHERS.keys()):
            redacted_text = redacted_text[:ent.start_char] + "[REDACTED]" + redacted_text[ent.end_char:]

    return redacted_text

@app.route('/redact', methods=['POST'])
def redact():
    """
    Endpoint to redact PII from text
    Expects JSON: {
        "text": "Text to redact",
        "matchers": ["EMAIL", "PHONE"] // optional
    }
    """
    data = request.json
    if not data or 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400

    # Get selected matchers from request, env var, or use None for all
    selected_matchers = data.get('matchers', os.getenv('DEFAULT_MATCHERS', '').split(','))
    if selected_matchers == ['']:  # Handle empty env var case
        selected_matchers = None

    try:
        redacted = redact_pii(data['text'], selected_matchers)
        return jsonify({
            'redacted_text': redacted,
            'matchers_used': selected_matchers or list(AVAILABLE_MATCHERS.keys())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/available-matchers', methods=['GET'])
def get_matchers():
    """Endpoint to list all available matchers and their descriptions"""
    return jsonify({
        'matchers': {
            name: info['description']
            for name, info in AVAILABLE_MATCHERS.items()
        },
        'default_ner_entities': DEFAULT_NER_ENTITIES
    })

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5005))
    app.run(host='0.0.0.0', port=port)
