FROM python:3.10

WORKDIR /app

RUN pip install jupyter pandas numpy matplotlib scikit-learn

EXPOSE 8888

CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=", "--NotebookApp.password="]
