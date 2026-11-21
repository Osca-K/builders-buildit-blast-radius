FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
WORKDIR /app
COPY selector.py comparison_equivalence.py comparison_value_equivalence.py primitive_comparisons.py index.json.gz ./
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/app/selector.py"]
