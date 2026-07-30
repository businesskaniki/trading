
from fastapi import FastAPI

app = FastAPI(title="Athena Quant Engine")


@app.get("/")
def root():
    return {"status": "running"}