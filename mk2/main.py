import logging
import json
from collections import defaultdict

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, WebSocket, Request, Depends, BackgroundTasks
from fastapi.templating import Jinja2Templates

from starlette.websockets import WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
import random

import threading
import schedule
import time
import asyncio

import json
import requests


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")

class Notifier:
    """
        Manages chat room sessions and members along with message routing
    """

    def __init__(self):
        self.connections: dict = defaultdict(dict)
        self.generator = self.get_notification_generator()
        self.user_access_info: dict = defaultdict(dict)     # 현재 접속중인 소켓 정보
        self.user_turn_count: dict = defaultdict(dict)      # user_access_info의 인덱스: 순서대로 접근하기 위해 선언한 변수
        self.room_game_start: dict = defaultdict(dict)
        self.recent_turn_user: dict = defaultdict(dict)
        self.board_size = 11                                # game_board size

    async def get_notification_generator(self):
        while True:
            message = yield
            msg = message["message"]
            room_name = message["room_name"]
            await self._notify(msg, room_name)

    def get_members(self, room_name):
        """해당 room에 있는 소켓 구하기"""
        # living_conn = []
        # for i in self.connections[room_name]:
        #     print(i)
        #     #i = json.loads(i)
        #     print(i.client_state.name)
        #     print("--21312312312312")
        #     if i.client_state.name == "CONNECTED":
        #         living_conn.append(i)
        #         print("asdasdasd")
        # print(living_conn)
        try:
            #living_conn = []
            # for i in self.connections[room_name]:
            #     i = json.dumps(i)
            #     print(i.client_state.name)
            #     print("--21312312312312")
            #     if i.client_state.name == "CONNECTED":
            #         living_conn.append(i)
            #return self.connections[room_name]
            # living_conn = []
            # for i in self.connections[room_name]:
            #     #print(i)
            #     if i.client_state.name == "CONNECTED":
            #         living_conn.append(i)
            # #print(living_conn)
            return self.connections[room_name]
        except Exception:
            return None

    async def push(self, msg: str, room_name: str = None):
        message_body = {"message": msg, "room_name": room_name}
        await self.generator.asend(message_body)

    async def send_to_room(self, room_name, send_info):
        """같은 방에 있는 사람에게 뿌려주기"""
        try:
            living_connections = []
            while len(self.connections[room_name]) > 0:
                websocket = self.connections[room_name].pop()
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_text(send_info)
                    living_connections.append(websocket)
                else:
                    print(websocket)
            self.connections[room_name] = living_connections
        except Exception as exception:
            print("예외는 ", exception)
        

    async def connect(self, websocket: WebSocket, room_name: str):
        """웹소켓 연결 설정"""

        await websocket.accept()
        if self.connections[room_name] == {} or len(self.connections[room_name]) == 0:
            self.connections[room_name] = []
        self.connections[room_name].append(websocket)

        print(f"CONNECTIONS : {self.connections[room_name]}")

   
    def remove(self, websocket: WebSocket, room_name: str):
        """방에서 퇴장한 user 정보 설정"""

        # 기존 딕셔너리에서 user_name 가져오고 해당 키 삭제. 이후 클라이언트로 user_name 전달
        # 이것은 턴을 위한 유저 정보
        send_userid = self.user_access_info[room_name].pop(websocket, None)

        # user가 나갔으면 해당 room에서 socket 지워주기
        if websocket in self.connections[room_name]:
            self.connections[room_name].remove(websocket)

        if len(self.connections[room_name]) == 0:
            print("이 방은 지웁니다.", room_name)
            del self.user_access_info[room_name]

        print(send_userid)

        print(
            f"CONNECTION REMOVED\nREMAINING CONNECTIONS : {self.connections[room_name]}"
        )

        return send_userid

    async def _notify(self, message: str, room_name: str):
        """자신의 채팅 다른사람에게 전달"""

         # 같은 방에 있는 사람에게 뿌려주기
        await self.send_to_room(room_name, message)


    async def _notCam(self, bytesimage: str, room_name: str):
        """자신의 캠 다른사람에게 전달"""

        # 같은 방에 있는 사람에게 뿌려주기
        await self.send_to_room(room_name, bytesimage)

    async def insert_user_access_info(self, info, room_name, userid, websocket):
        """접속한 유저정보 저장, client에게 해당 유저의 cam을 보여줄 수 있는 HTML 만들라고 전달"""


        print(userid)
        # 들어왔으니 그려라
        print("들어와라", websocket)
        print(info)

        # 같은 방에 있는 사람에게 뿌려주기
        await self.send_to_room(room_name, info)

    async def delete_frame(self, room_name, send_userid):
        """유저가 나갔을 때 자기 캠 지우기"""
        print("캠 지워주세요", send_userid)

        json_object = {
            "type": "delete_frame",
            "userid": send_userid, 
        }
        json_object = json.dumps(json_object)

        # 같은 방에 있는 사람에게 뿌려주기
        await self.send_to_room(room_name, json_object)

    def update_user_access_info(self, room_name):
        # 이번 턴 유저 아이디 설정
        get_conn_list = self.get_members(room_name)
        for i in get_conn_list:
            if i.client_state.name != "CONNECTED":
                self.connections[room_name].remove(i)
                self.user_access_info[room_name].pop(i, None)
        print("업데이트 후 남아있는건", self.user_access_info[room_name])

    def get_user_turn(self, user_turn: json, room_name: str):
        """유저의 턴 정보 전달"""

        print(self.user_access_info[room_name])
        self.update_user_access_info(room_name)
        user_lists = list(self.user_access_info[room_name].values())
        if(len(user_lists) <= 0):
            return ""

        if self.user_turn_count[room_name] >= len(user_lists):
            self.user_turn_count[room_name] = 0

        print("이번 유저는 ", self.user_turn_count[room_name], user_lists)

        user_turn["userid"] = user_lists[self.user_turn_count[room_name]]
        user_turn["type"] = "send_user_turn"
        self.recent_turn_user[room_name] = user_turn["userid"]
        print("유저 턴 줍니다~~~~~~~.", user_lists[self.user_turn_count[room_name]])
        

        # 다음 턴 유저 아이디 설정
        self.user_turn_count[room_name] += 1
        if self.user_turn_count[room_name] >= len(user_lists):
            self.user_turn_count[room_name] = 0

        # client에 보내기 위해 json으로 변환
        user_turn = str(json.dumps(user_turn))
        return user_turn
    
    async def check_users(self, room_name):
        print("호호홓")
        for i in self.connections[room_name]:
            if i.client_state.name != "CONNECTED":
                self.connections[room_name].remove(i)
                send_userid = self.user_access_info[room_name].pop(i, None)
                print("지워라", send_userid)
                await notifier.delete_frame(room_name, send_userid)


    async def game_server_request(self, room_name, path, method, params):
        """게임서버 호출하여 데이터를 받아옴"""
        print(room_name, path, method)

        api_host = "http://localhost:7777/"                                                  # 서버 주소
        headers = {'Content-Type': 'application/json', 'charset': 'UTF-8', 'Accept': '*/*'}  # http 헤더
        url = api_host + path                                                                # 상세 경로
        body = params                                                                        # http body
        response = ""                                                                        # http response
        user_lists = []                                                                      # 해당 room에 있는 user list
        send_data = ""                                                                       # 보낼 데이터
        
        body["roomId"] = room_name
        # 경로에 따른 전달 값 설정
        if path == "check":
            send_data = json.dumps(body, ensure_ascii=False, indent="\t").encode('utf-8')
        elif path == "init":
            #self.update_user_access_info(room_name)
            user_lists = list(self.user_access_info[room_name].values())
            body["users"] = user_lists
            body["size"] = self.board_size
            send_data = json.dumps(body, ensure_ascii=False, indent="\t")

        print(url)
        print(send_data)
        print("구분선====================")

        # http method에 따른 처리
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, data = send_data)
            elif method == 'POST':
                response = requests.post(url, headers=headers, data = send_data)
            
            print(response.text)
            
            # 같은 방에 있는 사람에게 뿌려주기
            await self.send_to_room(room_name, response.text)

        except Exception as exception:
            print(exception)

notifier = Notifier()
# controller routes
@app.get("/test/{room_name}/{user_name}")
async def get(request: Request, room_name, user_name):
    print("in index")
    return templates.TemplateResponse(
        "chat_room.html",
        {"request": request, "room_name": room_name, "user_name": user_name},
    )

@app.websocket("/ws/{room_name}")
async def websocket_endpoint(
    websocket: WebSocket, room_name, background_tasks: BackgroundTasks
):
    
    print()
    print()
    print()
    print("in websocket")
    #print(websocket.client_state.name)
    await notifier.connect(websocket, room_name)
    try:
        timer = ""
        await notifier.check_users(room_name)
        while True:
            data = await websocket.receive_text()
            d = json.loads(data)
            d["room_name"] = room_name
            room_members = (notifier.get_members(room_name) if notifier.get_members(room_name) is not None else [])

            if websocket not in room_members:
                print("USER NOT IN ROOM MEMBERS: RECONNECTING")
                print("업슨ㄴ 웹소켓은  ",websocket)
                print("룸멤버는  ",room_members)
                await notifier.connect(websocket, room_name)
                notifier.user_access_info[room_name][websocket] = d["userid"]
                await notifier.insert_user_access_info(f"{data}", room_name, d["userid"], websocket)
                # 게임보드 보내고
                # 게임 시작 버튼 제거하고

            if d["type"] == 'video':
                await notifier._notCam(f"{data}", room_name)
            elif d["type"] == 'message':
                await notifier._notify(f"{data}", room_name)
            elif d["type"] == 'info':
                notifier.user_access_info[room_name][websocket] = d["userid"]
                print(notifier.user_access_info[room_name])
                await notifier.insert_user_access_info(f"{data}", room_name, d["userid"], websocket)
            elif d["type"] == 'send_user_turn':
                get_user_turn = notifier.get_user_turn(d, room_name)
                if get_user_turn != "":
                    await notifier.send_to_room(room_name, get_user_turn)
            elif d["type"] == 'game_server':
                print("게임서버 호출하러 갑니다.")
                path = d["path"]
                method = d["method"]
                params = d["params"]
                await notifier.game_server_request(room_name, path, method, params)
            elif d["type"] == "game_start":
                print("게임시작하니 버튼 지워주세요.")
                notifier.user_turn_count[room_name] = 0
                notifier.room_game_start[room_name] = 1
                await notifier.send_to_room(room_name, f"{data}")


    except WebSocketDisconnect:
        """소켓 연결이 끊어졌을 시"""

        # 연결정보 삭제
        get_user_id = notifier.remove(websocket, room_name)

        # 게임이 진행중이고 내 턴이 진행중일 때 연결이 끊어졌다면 남은 사람들에게 턴을 넘겨야 한다.
        if notifier.room_game_start[room_name] == 1 and get_user_id == notifier.recent_turn_user[room_name] :
            get_user_turn = notifier.get_user_turn(d, room_name)
            if get_user_turn != "":
                await notifier.send_to_room(room_name, get_user_turn)
        # 다시 참여 하러면 게임보드 보내줘야함
        # 또한 게임시작 버튼 지워야 한다.

        # 연결이 끊어졌으니 내 비디오를 지우라고 전송
        await notifier.delete_frame(room_name, get_user_id)
        #await websocket.close()
