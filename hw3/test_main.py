from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_example():
    r = client.post("/calculate/", json={"numbers": [5, 3, 10], "delays": [1, 2, 0.5]})
    assert r.status_code == 200
    body = r.json()
    assert [i["square"] for i in body["results"]] == [25, 9, 100]
    assert 2 <= body["total_time"] < 2.5
    assert body["parallel_faster_than_sequential"] is True
