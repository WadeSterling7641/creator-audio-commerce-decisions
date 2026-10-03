import uvicorn

from creator_audio.service import create_app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("run_service:app", host="127.0.0.1", port=8000, reload=False)
