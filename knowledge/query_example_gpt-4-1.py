import asyncio
import json

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
    
    # Generalized schema utilizing a uniform array of key-value objects
    general_capital_tool = {
        "type": "function",
        "function": {
            "name": "submit_capitals_list",
            "description": "Submit a comprehensive list of all requested countries and their corresponding capitals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "countries_and_capitals": {
                        "type": "array",
                        "description": "List containing pairs of country names and their capitals.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "country": {"type": "string", "description": "The name of the country."},
                                "capital": {"type": "string", "description": "The capital city of the country."}
                            },
                            "required": ["country", "capital"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["countries_and_capitals"],
                "additionalProperties": False
            }
        }
    }

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
        tools=[general_capital_tool],
        tool_choice={"type": "function", "function": {"name": "submit_capitals_list"}}
    )
    
    try:
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            # Parse the model's array output
            raw_arguments = json.loads(tool_calls[0].function.arguments)
            data_list = raw_arguments.get("countries_and_capitals", [])
            
            # Map the array elements into your desired flat dictionary structure
            flat_result = {item["country"]: item["capital"] for item in data_list}
            
            # Return it serialized as a clean JSON string
            return json.dumps(flat_result)
    except (IndexError, AttributeError, KeyError, json.JSONDecodeError):
        pass

    return (response.choices[0].message.content or "").strip()

async def main() -> None:
    text = await query_gpt41(
        "Be concise.",
        "Capital cities of France, Germany, Japan, and Italy are?",
    )
    print(text)


if __name__ == "__main__":
    asyncio.run(main())