FROM continuumio/miniconda3

WORKDIR /app

RUN conda install -c conda-forge spacy flask

# Download the English model (efficiency model)
#RUN python -m spacy download en_core_web_sm

# Download the English model (accuracy model)
#RUN python -m spacy download en_core_web_trf

RUN python -m spacy download en_core_web_md

# Copy the rest of the application
COPY . .

# Expose the port for the Flask app
EXPOSE 5005

# Run the Flask app
CMD ["python", "redaction_service.py"]

