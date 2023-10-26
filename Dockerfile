FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y curl
RUN mkdir /src
COPY requirements.txt /src
WORKDIR /src
RUN pip install -r /src/requirements.txt

COPY crypto.py /src
COPY count_words.py /src
COPY df_enc.csv /src
COPY run.sh /src

CMD ./run.sh
