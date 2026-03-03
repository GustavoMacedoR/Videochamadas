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

        msg_type = data.get('type')

        if msg_type == 'chat':
            # Only relay name + message; discard any other fields for safety
            payload = {
                'type': 'chat',
                'name': str(data.get('name', 'Anônimo'))[:80],
                'message': str(data.get('message', ''))[:1000],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'chat.message', 'sender': self.channel_name, 'data': payload},
            )
            return

        if msg_type == 'raise_hand':
            payload = {
                'type': 'hand_raise',
                'client_id': str(data.get('client_id', ''))[:40],
                'name': str(data.get('name', 'Anônimo'))[:80],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'hand.raise', 'sender': self.channel_name, 'data': payload},
            )
            return

        if msg_type == 'lower_hand':
            payload = {
                'type': 'hand_lower',
                'client_id': str(data.get('client_id', ''))[:40],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'hand.lower', 'sender': self.channel_name, 'data': payload},
            )
            return

        # Relay all other signaling messages to the room group, include sender to avoid loops
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'signal.message',
                'sender': self.channel_name,
                'data': data,
            }
        )

    async def chat_message(self, event):
        # Don't echo back to the sender (they already rendered the message locally)
        if event.get('sender') == self.channel_name:
            return
        await self.send(text_data=json.dumps(event.get('data')))

    async def hand_raise(self, event):
        # Echo to everyone including sender so all queues stay in sync
        await self.send(text_data=json.dumps(event.get('data')))

    async def hand_lower(self, event):
        await self.send(text_data=json.dumps(event.get('data')))

    async def signal_message(self, event):
        # Don't send message back to originating channel
        if event.get('sender') == self.channel_name:
            return
        await self.send(text_data=json.dumps(event.get('data')))
