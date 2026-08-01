FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir httpx scikit-learn numpy

COPY experiments/ /app/experiments/

CMD ["python", "-m", "experiments.simulation.harness", \
     "--db", "experiments/experiment_data.db", \
     "--methodology", "bin_cal", \
     "--output", "/app/results/results_bin_cal.jsonl"]
