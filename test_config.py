import os
import json


def load_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            stt_config = config.get("stt", {})
    return stt_config

def test_load():
    whisper_url = test['whisper_server_url']
    print(whisper_url)
    print(type(test['sampling_rate']))

if __name__ == '__main__':
    test = load_config()
    
    test_load()