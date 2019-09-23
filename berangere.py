import discord
from discord.ext import commands
import asyncio
import os
import sys
import time
import json
import argparse
from datetime import datetime
import sqlite3
import pafy
import gtts
import tempfile
#Requires discord.py pynacl youtube-dl pafy gtts

def escapeshellarg(arg):
    return "\\'".join("'" + p + "'" for p in arg.split("'"))

class Berangere(commands.Bot):
    
    def __init__(self):
        commands.Bot.__init__(self, command_prefix=config['command_prefix'], guild_subscriptions=True)
        self.setup_commands()
        self.saturation = dict()
        self.volume = dict()
        self.loops =list()
        self.follow = dict()
        if not os.path.isfile("bot.db"):
            conn = sqlite3.connect("bot.db")
            cur = conn.cursor()
            cur.execute("""create table users(
                                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT,
                                last_seen TEXT
                            )""")
            conn.commit()
            

    async def is_authorized_channel(ctx):
        """
        Returns true if the name of the channel is in AUTHORIZED_CHANNEL_NAMES
        """
        if len(config["authorized_channel_names"]) == 0:
            return True
        channel = ctx.channel
        if channel.type == discord.ChannelType.private:
            return True
        try:
            return ctx.channel.name in config['authorized_channel_names']
        except AttributeError as ex:
            return False

    async def is_guild_admin(ctx):
        """
        Returns true if the user that invoked the command is an admin
        """
        if type(ctx.author) is discord.Member:
            return ctx.author.guild_permissions.administrator
        else:
            return False

    def is_connected(ctx):
        """
        Returns true if the bot is connected in a channel of the same guild as the user that invoked the context
        """
        if ctx.guild.voice_client != None:
            return True
        return False

    def is_playing(ctx):
        """
        Returns true if the bot is currently playing sound in the same guild as the user that invoked the context
        """
        if ctx.voice_client != None:
            return ctx.voice_client.is_playing()
        return False

    def stop(ctx):
        """
        Stops the sound the bot is currently playing in the guild of the user that invoked the context
        If the command implied that the bot had to disconnect after playing, the bot will disconnect as it finished playing the sound of the command.
        """
        if ctx.guild.voice_client != None:
            ctx.guild.voice_client.stop()

    def setup_commands(self):
        """
        Adds the commands to the bot
        """

        #Global checks (run before every command)
        self.add_check(Berangere.is_authorized_channel)

        @self.command()
        async def ping(ctx):
            """
            Pong
            """
            await ctx.send("Pong")

        @self.command()
        async def sons(ctx):
            """
            Displays the list of sounds the bot knows
            """
            files = ['0'+os.path.splitext(f)[0] for f in os.listdir(config['sounds_base_dir']) if os.path.splitext(f)[1] == ".mp3"]
            ret = config["separator"].join(files)
            last_cut = 0
            while len(ret[last_cut:]) > 1999:
                next_cut = ret.rfind(config["separator"], last_cut, last_cut+1999)
                msg = ret[last_cut:next_cut]
                await ctx.send(msg)
                last_cut = next_cut+len(config["separator"])
            msg = ret[last_cut:]
            await ctx.send(msg)
                
        
        @self.command(aliases=["summon"])
        @commands.check(Berangere.is_guild_admin)
        async def move(ctx, channel_name=None):
            """
            Moves the bot to the channel given in parameter
            """
            # if Berangere.is_playing(ctx):
            #     await ctx.send("Sorry but the bot is already busy playing")
            #     return
            if channel_name==None:
                if ctx.author.voice.channel != None:
                    dst_channel = ctx.author.voice.channel
            else:
                channel = [channel for channel in ctx.guild.voice_channels if channel.name==channel_name]
                if len(channel) > 0:
                    dst_channel = channel[0]
                else:
                    await ctx.send("Sorry but I do not know this channel")
                    return
            if ctx.voice_client != None:
                await ctx.voice_client.move_to(dst_channel)
            else:
                await dst_channel.connect()
            
        @self.command()
        async def stop(ctx):
            """
            Check if the bot is playing in the same channel as the user and disconnects it from the channel
            """
            if ctx.guild in self.loops:
                self.loops.remove(ctx.guild)
            if Berangere.is_playing(ctx):
                Berangere.stop(ctx)
            else:
                await ctx.send("There is nothing to stop")
        
        @self.command()
        async def kick(ctx):
            """
            Kick the bot if connected in the same guild as the user
            """
            if ctx.voice_client != None:
                await ctx.voice_client.disconnect()

        @self.command()
        async def playAll(ctx, directory=None):
            """
            Plays all sounds in the default directory or in the directory specified
            """
            if directory == None:
                directory = config['sounds_base_dir']
            else:
                directory = "./"+directory
            try:
                must_disconnect=False
                all_songs = [f for f in os.listdir(f"{directory}") if os.path.splitext(f)[-1] == ".mp3"]
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                await self.playSounds(ctx=ctx,directory=directory,sounds=all_songs, disconnect_after=must_disconnect)
            except commands.BadArgument as ex:
                print(ex)
                await ctx.send(ex)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                #Not member of the guild or busy playing in same guild
                print(ex)
                await ctx.send("Sorry but the bot is in another channel")
                return

        @self.command(aliases=["yt"])
        async def youtube(ctx, url):
            """
            Plays sound from a youtube video.
            """
            try:
                video = pafy.new(url)
                best = video.getbestaudio()
                playurl = best.url
                must_disconnect = False
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                await ctx.send(f"Playing {video.title} for {video.duration}")
                await self.playURL(ctx, playurl, must_disconnect)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                print(ex)
                #Not member of the guild or busy playing in same guild
                await ctx.send("Sorry but the bot is in another channel")
                return

        @self.command()
        async def ls(ctx, *sounds):
            """
            Plays the list of sounds sounds simultaneously
            """
            try:
                must_disconnect=False
                user_voice_channel = ctx.author.voice.channel
                sounds = [sound+".mp3" for sound in sounds if os.path.isfile(f"{config['sounds_base_dir']}/{sound}.mp3")]
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                await self.playSounds(ctx=ctx,directory=config['sounds_base_dir'],sounds=sounds, disconnect_after=must_disconnect)
            except commands.BadArgument as ex:
                print(ex)
                await ctx.send(ex)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                print(ex)
                #Not member of the guild or busy playing in same guild
                await ctx.send("Sorry but the bot is in another channel")
                return

        @self.command()
        async def mu(ctx, sound, number, interval):
            """
            Plays the given sound {number} times at an interval of {interval} milliseconds
            """
            try:
                must_disconnect=False
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                if not os.path.isfile(f"{config['sounds_base_dir']}/{sound}.mp3"):
                    await ctx.send("This sound does not exist")
                    return
                if str(number).isdigit() and str(interval).isdigit():
                    repeat=int(number)
                    delay = float(interval)/1000
                    plays_done = 0
                    loop = asyncio.get_running_loop()
                    before_options = f'-filter_complex "volume={self.saturation.get(ctx.guild, 1)}"'
                    volume=self.volume.get(ctx.guild, 1)
                    def repeat_or_disconnect(err):
                        if ctx.guild not in self.loops:
                            return
                        nonlocal plays_done
                        plays_done = plays_done + 1
                        if err != None:
                            if ctx.guild in self.loops:
                                self.loops.remove(ctx.guild)
                            return
                        if plays_done == repeat:
                            if ctx.guild in self.loops:
                                self.loops.remove(ctx.guild)
                            if must_disconnect:
                                loop.create_task(ctx.voice_client.disconnect(force=True))
                        else:
                            time.sleep(delay)
                            audio_source = discord.FFmpegPCMAudio(options=before_options, source=f"{config['sounds_base_dir']}/{sound}.mp3")
                            audio_volume = discord.PCMVolumeTransformer(audio_source, volume=volume)
                            ctx.voice_client.play(audio_volume, after=repeat_or_disconnect)

                    audio_source = discord.FFmpegPCMAudio(options=before_options, source=f"{config['sounds_base_dir']}/{sound}.mp3")
                    audio_volume = discord.PCMVolumeTransformer(audio_source, volume=volume)
                    if ctx.guild not in self.loops:
                        self.loops.append(ctx.guild)
                    ctx.voice_client.play(audio_volume, after=repeat_or_disconnect)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                print(ex)
                #Not member of the guild or busy playing in same guild
                await ctx.send("Sorry but the bot is in another channel")
                return

        @self.command()
        async def saturation(ctx, value):
            """
            Sets the saturation of the audio streams of the bot
            """
            try:
                self.saturation[ctx.guild] = float(value)
                await ctx.send(f"Saturation set to {value}")
            except:
                await ctx.send("Value must be a number")
        @self.command()
        async def volume(ctx, value):
            """
            Sets the volume of the audio streams of the bot
            """
            try:
                self.volume[ctx.guild] = float(value)
                await ctx.send(f"Volume set to {value}")
            except:
                await ctx.send("Value must be a number")
                
        @self.command()
        async def lastSeen(ctx, username):
            """
            Shows when user has been last seen
            """
            conn = sqlite3.connect("bot.db")
            curs = conn.cursor()
            curs.execute("SELECT last_seen FROM users WHERE name = ?", (username,))
            user = curs.fetchone()
            if user is None:
                await ctx.send(f"{username}? Never heard of such a name...")
            else:
                await ctx.send(f"{username} was last seen on {user[0]}")

        @self.command()
        async def say(ctx, *words):
            """
            Speaks out loud the phrase given
            Use -xx as the first word to set the language
            """
            if len(words) < 1:
                return
            language = "en"
            phrase=""
            if words[0][0] == "-":
                language=words[0][1:]
                phrase = ' '.join(words[1:])
            else:
                phrase = ' '.join(words)
            tts = gtts.gTTS(phrase, lang=language)
            must_disconnect = False
            try:
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                buf = tempfile.TemporaryFile()
                tts.write_to_fp(buf)
                buf.seek(0)
                loop = asyncio.get_running_loop()
                before_options = f'-filter_complex "volume={self.saturation.get(ctx.guild, 1)}"'
                def disconnect(error):
                    if must_disconnect == True:
                        loop.create_task(ctx.voice_client.disconnect(force=True))
                audio_source = discord.FFmpegPCMAudio(source=buf,pipe=True, before_options=before_options)
                audio_volume = discord.PCMVolumeTransformer(audio_source, volume=self.volume.get(ctx.guild, 1))
                ctx.voice_client.play(audio_volume, after=disconnect)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                #Not member of the guild or busy playing in same guild
                print(ex)
                await ctx.send("Sorry but the bot is in another channel")
                return

        @self.command()
        async def spotify(ctx):
            """
            Lets the bot diffuse spotify songs
            """
            must_disconnect = False
            try:
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                loop = asyncio.get_running_loop()
                def disconnect(error):
                    if must_disconnect == True:
                        loop.create_task(ctx.voice_client.disconnect(force=True))
                audio_source = discord.FFmpegPCMAudio(source="default", before_options="-f alsa")
                ctx.voice_client.play(audio_source, after=disconnect)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                #Not member of the guild or busy playing in same guild
                print(ex)
                await ctx.send("Sorry but the bot is in another channel")
                return
        @self.command(aliases=['youreit'])
        @commands.check(Berangere.is_guild_admin)
        async def follow(ctx, username=None, song=None):
            """
            The bot will follow the user given
            """
            if username == None:
                if ctx.guild in self.follow:
                    self.follow.pop(ctx.guild)
                await ctx.send(f"The bot will stop following")
            else:
                self.follow[ctx.guild] = {'username':username, 'song':song}
                await ctx.send(f"The bot will now follow {username}")

    async def playURL(self, ctx, url, disconnect_after=True):
        before_options = f'-filter_complex "volume={self.saturation.get(ctx.guild, 1)}"'
        volume=self.volume.get(ctx.guild, 1)
        audio_source = discord.FFmpegPCMAudio(before_options=before_options, source=url)
        audio_volume = discord.PCMVolumeTransformer(audio_source, volume=volume)
        loop = asyncio.get_running_loop()
        def disconnect(error):
            if disconnect_after == True:
                loop.create_task(ctx.voice_client.disconnect(force=True))
        ctx.voice_client.play(audio_volume, after=disconnect)

    async def playSounds(self, ctx,directory, sounds, disconnect_after=True):
        if len(sounds) == 0:
            raise commands.BadArgument("Sorry but there is no sound to play:(")
        elif len(sounds) > 1:
            nb_sounds = len(sounds)
            source_str = ""
            for sound in sounds[1:]:
                song = escapeshellarg(directory + "/" + sound)
                source_str += f"-i {song} "
            before_options = f'-filter_complex "amix=inputs={nb_sounds}:duration=longest[a];[a]volume={self.saturation.get(ctx.guild, 1)}" {source_str}'
        else:
            before_options = f'-filter_complex "volume={self.saturation.get(ctx.guild, 1)}"'
       
        volume=self.volume.get(ctx.guild, 1)
        audio_source = discord.FFmpegPCMAudio(before_options=before_options, source=f"{directory}/{sounds[0]}")
        audio_volume = discord.PCMVolumeTransformer(audio_source, volume=volume)
        loop = asyncio.get_running_loop()
        def disconnect(error):
            if disconnect_after == True:
                loop.create_task(ctx.voice_client.disconnect(force=True))
        ctx.voice_client.play(audio_volume, after=disconnect)
    async def on_command_error(self, ctx, exc):
        """
        Called when an uncaught exception is thrown in a command
        """
        if type(exc) is commands.CommandNotFound:
            #When a command does not exist, try to play the sound named like the command.
            command = ctx.invoked_with
            if not os.path.isfile(f"{config['sounds_base_dir']}/{command}.mp3"):
                await ctx.send(f"{command} is not a valid sound.")
                return
            try:
                must_disconnect=False
                if ctx.voice_client == None:
                    await ctx.author.voice.channel.connect()
                    must_disconnect=True
                elif ctx.voice_client.channel != ctx.author.voice.channel:
                    #If not in same channel, check permissions
                    if type(ctx.author) is not discord.Member or not ctx.author.guild_permissions.administrator:
                        #User has no admin rights. Refuse to play sound
                        await ctx.send("Sorry but the bot is in another channel")
                        return
                user_voice_channel = ctx.author.voice.channel
                await self.playSounds(ctx=ctx,directory=config['sounds_base_dir'], sounds=[command+".mp3"], disconnect_after=must_disconnect)
            except AttributeError as ex:
                print(ex)
                await ctx.send("Try sending from a channel on your guild")
            except discord.errors.ClientException as ex:
                #Not member of the guild or busy playing in same guild
                print(ex)
                await ctx.send("Sorry but the bot is in another channel")
                return
        elif type(exc) is commands.MissingRequiredArgument:
            await ctx.send(ctx.command.usage)
        else:
            print(exc)
    async def on_voice_state_update(self, member, before, after):
        chan = [c for c in member.guild.text_channels if c.name =="voice-log"]
        if len(chan) == 0:
            return
        chan = chan[0]
        if before.channel == after.channel:
            return
        if self.user == member:
            return
        now = datetime.now().strftime("%H:%M:%S")
        state=""
        if before.channel == None:
            #Connected
            state="connected"
            await chan.send(f"**{member.display_name}** connected to channel **{after.channel.name}** at {now}")
        elif after.channel == None:
            #Disconnected
            state="disconnected"
            await chan.send(f"**{member.display_name}** disconnected from channel **{before.channel.name}** at {now}")
            conn = sqlite3.connect("bot.db")
            curs = conn.cursor()
            curs.execute("UPDATE users set last_seen = ? WHERE name=?", (datetime.now().strftime('%d/%m/%Y %H:%M:%S'),member.name))
            if curs.rowcount == 0:
                curs.execute("INSERT INTO users (name, last_seen) values(?,?)", (member.name, datetime.now().strftime('%d/%m/%Y %H:%M:%S')))
            conn.commit()
        else:
            #changed channel
            state="changed"
            await chan.send(f"**{member.display_name}** moved from channel **{before.channel.name}** to **{after.channel.name}** at {now}")
       
        if state in ("connected", "changed"):
            if member.guild in self.follow: 
                if member.name == self.follow[member.guild]['username']:
                    if member.guild.voice_client == None:
                        await after.channel.connect()
                    else:
                        await member.guild.voice_client.move_to(after.channel)
                    if self.follow[member.guild]['song'] != None and not member.guild.voice_client.is_playing():
                        member.guild.voice_client.play(discord.FFmpegPCMAudio(f"{config['sounds_base_dir']}/{self.follow[member.guild]['song']}.mp3"))
                return
            
        if member.guild.voice_client == None:
            return
        if member.guild.voice_client.is_playing():
            return
        bot_channel = member.guild.voice_client.channel
        sentence = ""
        if state == "disconnected":
            if bot_channel == before.channel:
                #Dire "déconnexion...."
                sentence = f"{member.name} disconnected from your channel"
        elif state == "changed":
            if bot_channel == before.channel:
                #Dire déconnexion...
                sentence = f"{member.name} disconnected from your channel"
            elif bot_channel == after.channel:
                #Dire connexion
                sentence = f"{member.name} connected to your channel"
        elif state == "connected":
            if bot_channel == after.channel:
                #Dire connexion
                sentence = f"{member.name} connected to your channel"
        tts = gtts.gTTS(sentence, lang="fr-ca")
        tf = tempfile.TemporaryFile()
        tts.write_to_fp(tf)
        tf.seek(0)
        audio_source = discord.FFmpegPCMAudio(tf, pipe=True)
        member.guild.voice_client.play(audio_source)
        

    async def on_ready(self):
        print(f"Bot connected with name {self.user.name}")

    async def on_message(self, message):
        if message.content.startswith(config['command_prefix']):
            await super().on_message(message)
            return
        if message.channel.name not in config['authorized_channel_names'] or message.author == self.user:
            return
        if config['aggressive']:
            await message.channel.send(f"I'm a bot you dumbass. If you're here for help type \"{config['command_prefix']}help\" like everyone else")
            await message.add_reaction("😡")


if __name__ == "__main__":
    conf_file = open("config.json", "r")
    config = json.load(conf_file)
    parser = argparse.ArgumentParser(description="Discord bot that plays sound files.")
    parser.add_argument("-k","--key", metavar="key", type=str, nargs=1, help="Name of the key as written in the config file.")
    args = parser.parse_args()
    keyname = args.key
    if keyname != None:
        try:
            KEY=config['keys'][keyname[0]]
        except:
            print(f"There is no key named {keyname[0]}. Please check config.json")
            sys.exit()
    else:
        try:
            KEY = list(config['keys'].values())[0]
        except:
            print("No key found in config.json")
            sys.exit()
    ber = Berangere()
    ber.run(KEY)
