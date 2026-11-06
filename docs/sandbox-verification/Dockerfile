FROM trace-tutor-runner:1
USER 0:0
RUN apt-get update && apt-get install --no-install-recommends -y python3-pip \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages Django==5.2.17 html5lib==1.1 beautifulsoup4==4.15.0
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
COPY tutor /app/tutor
COPY verify.py /app/verify.py
WORKDIR /app
CMD ["python3", "verify.py"]
