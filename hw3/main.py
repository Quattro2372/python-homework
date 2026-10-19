import asyncio
import time

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

app = FastAPI()


class CalculateRequest(BaseModel):
    numbers: list[float] = Field(..., min_length=1)
    delays: list[float] = Field(..., min_length=1)


class ItemResult(BaseModel):
    number: float
    square: float
    delay: float
    time: float


class CalculateResponse(BaseModel):
    results: list[ItemResult]
    total_time: float
    parallel_faster_than_sequential: bool


async def square_with_delay(number: float, delay: float) -> ItemResult:
    start = time.perf_counter()
    await asyncio.sleep(delay)

    square = number * number
    return ItemResult(
        number=number,
        square=square,
        delay=delay,
        time=round(time.perf_counter() - start, 2),
    )


@app.post("/calculate/", response_model=CalculateResponse)
async def calculate(data: CalculateRequest) -> CalculateResponse:
    start = time.perf_counter()

    results = await asyncio.gather(
        *(square_with_delay(n, d) for n, d in zip(data.numbers, data.delays))
    )

    total_time = time.perf_counter() - start
    sequential_time = sum(data.delays)

    return CalculateResponse(
        results=results,
        total_time=round(total_time, 2),
        parallel_faster_than_sequential=total_time < sequential_time,
    )
