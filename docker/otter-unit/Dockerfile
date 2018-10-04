# otter-unit exists solely to run the unit tests on the Jenkins server.
FROM python:2.7
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY . ./
RUN pip install -e .


CMD ["make", "unit"]
