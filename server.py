"""启动入口：python server.py"""
import logging

from avalon import config, llm
from avalon.app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
    print(f"阿瓦隆游戏服务器启动 → http://localhost:{config.PORT}")
    print(f"AI 后端：{llm.describe()}")
    create_app().run(debug=False, port=config.PORT, threaded=True)
