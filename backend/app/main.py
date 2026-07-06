from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(title="ATLAS Control")


app = create_app()
