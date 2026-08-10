import json

import nextsteam_core

request = json.dumps(
    {
        "seeds": [{"appid": 1, "weight": 1.0}],
        "intent": {
            "lane_weights": {
                "mechanics": 1.0,
                "narrative": 0.0,
                "vibe": 0.0,
                "structure_loop": 0.0,
            },
            "include": [],
            "exclude": [],
            "text": None,
        },
        "limit": 1,
    }
)
candidates = json.dumps(
    [
        {
            "game_id": 2,
            "lanes": {
                "mechanics": 0.8,
                "narrative": 0.0,
                "vibe": 0.0,
                "structure_loop": 0.0,
            },
            "concepts": [],
            "evidence_ids": [],
        }
    ]
)
result = json.loads(nextsteam_core.rank_json(request, candidates))
assert result["results"][0]["game_id"] == 2
