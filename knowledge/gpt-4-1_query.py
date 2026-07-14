import asyncio

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

AZURE_ENDPOINT = "https://ai-foundry-rnd-dev.cognitiveservices.azure.com/"
GPT41_DEPLOYMENT = "gpt-4.1-limitless"
AZURE_API_VERSION = "2024-12-01-preview"
AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


async def query_gpt41(system_prompt: str, user_prompt: str) -> str:
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), AZURE_TOKEN_SCOPE
    )
    client = AsyncAzureOpenAI(
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        azure_ad_token_provider=token_provider,
        timeout=60,
        max_retries=0,
    )
    response = await client.chat.completions.create(
        model=GPT41_DEPLOYMENT,
        max_completion_tokens=13107,
        temperature=1.0,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()


async def main() -> None:
    text = await query_gpt41(
        "Be concise.",
        "Reply with one short sentence about SPDX licenses.",
    )
    print(text)


if __name__ == "__main__":
    asyncio.run(main())