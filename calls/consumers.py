from channels.generic.websocket import AsyncWebsocketConsumer
import json


class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.group_name = f'call_{self.room_name}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return

        # Relay signaling messages to the room group, include sender to avoid loops
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'signal.message',
                'sender': self.channel_name,
                'data': data,
            }
        )

    async def signal_message(self, event):
        # Don't send message back to originating channel
        if event.get('sender') == self.channel_name:
            return
        await self.send(text_data=json.dumps(event.get('data')))
