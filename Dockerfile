FROM continuumio/miniconda3

WORKDIR /app

# Add build argument with default value
ARG SPACY_MODEL=en_core_web_md
ENV SPACY_MODEL=$SPACY_MODEL

RUN conda install -c conda-forge spacy flask python-dotenv

RUN python -m spacy download $SPACY_MODEL

# Copy the rest of the application
COPY . .

# Expose the port for the Flask app
EXPOSE 5005

# Run the Flask app
CMD ["python", "redaction_service.py"]

