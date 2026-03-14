from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from config import settings

app = FastAPI()

VERIFY_TOKEN = settings.META_WA_VERIFY_TOKEN

@app.get("/webhook")
async def verify(request: Request):

    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    return {"status": "verification failed"}


@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print(data)
    return {"status": "received"}
