# This is Part 1 - Imports and Basic Setup
# Copy everything from Part 1-6 into one bot.py file

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import secrets
from datetime import datetime
import asyncio
from flask import Flask
from threading import Thread

load_dotenv()

# Flask keeps bot alive on Render
app = Flask('')

@app.route('/')
def home():
    return "<h1 style='text-align:center; margin-top:50px; font-family:Arial;'>Bot is Active ✅</h1>"

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Bot Config
PREFIX = os.getenv('PREFIX', '$')
DATABASE_URL = os.getenv('DATABASE_URL')
TOKEN = os.getenv('TOKEN')

# Colors
MM_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245

# MM Tiers - Updated to dollar amounts
MM_TIERS = {
    '1_50': {
        'name': '$1-$50 Middleman',
        'range': '$1-$50',
        'description': 'Small trades and items',
        'emoji': '🟢',
        'level': 1
    },
    '50_100': {
        'name': '$50-$100 Middleman',
        'range': '$50-$100',
        'description': 'Medium value trades',
        'emoji': '🔵',
        'level': 2
    },
    '100_250': {
        'name': '$100-$250 Middleman',
        'range': '$100-$250',
        'description': 'High value trades',
        'emoji': '🟣',
        'level': 3
    },
    '250_plus': {
        'name': '$250+ Middleman',
        'range': '$250+',
        'description': 'Premium and exclusive trades',
        'emoji': '💎',
        'level': 4
    }
}

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# This is Part 2 - Database Helper Functions
# These handle all PostgreSQL operations

def get_db():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL)

def get_config(key):
    """Get config value from database"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT value FROM bot_config WHERE key = %s", (key,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result['value'] if result else None
    except:
        return None

def set_config(key, value):
    """Save config value to database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_config (key, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
    """, (key, str(value), str(value)))
    conn.commit()
    cur.close()
    conn.close()

def get_all_mm_roles():
    """Get all MM role IDs from database"""
    roles = {}
    for tier in ['1_50', '50_100', '100_250', '250_plus']:
        value = get_config(f'mm_role_{tier}')
        if value and value != '0':
            roles[tier] = int(value)
    return roles

def create_ticket_db(channel_id, user_id, ticket_type, **kwargs):
    """Create ticket in database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (channel_id, user_id, ticket_type, tier, trader, giving, 
                           receiving, both_join, tip, reason, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        channel_id, user_id, ticket_type,
        kwargs.get('tier'), kwargs.get('trader'), kwargs.get('giving'),
        kwargs.get('receiving'), kwargs.get('both_join'), kwargs.get('tip'),
        kwargs.get('reason'), kwargs.get('details')
    ))
    conn.commit()
    cur.close()
    conn.close()

def get_ticket_db(channel_id):
    """Get ticket from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tickets WHERE channel_id = %s", (channel_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result

def claim_ticket_db(channel_id, user_id):
    """Mark ticket as claimed in database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = %s, status = 'claimed' WHERE channel_id = %s", (user_id, channel_id))
    conn.commit()
    cur.close()
    conn.close()

def unclaim_ticket_db(channel_id):
    """Mark ticket as unclaimed in database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = NULL, status = 'open' WHERE channel_id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()

def delete_ticket_db(channel_id):
    """Delete ticket from database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE channel_id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()

def increment_mm_stats(user_id):
    """Add 1 to MM's completed ticket count"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mm_stats (user_id, tickets_completed, last_updated)
        VALUES (%s, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET 
            tickets_completed = mm_stats.tickets_completed + 1,
            last_updated = CURRENT_TIMESTAMP
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_mm_stats(user_id):
    """Get MM stats for a user"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM mm_stats WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result if result else {'user_id': user_id, 'tickets_completed': 0}

def get_mm_leaderboard(limit=10):
    """Get top MM users"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT user_id, tickets_completed 
        FROM mm_stats 
        ORDER BY tickets_completed DESC 
        LIMIT %s
    """, (limit,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def get_mm_rank(user_id):
    """Get user's rank among all MMs"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) + 1 as rank
        FROM mm_stats
        WHERE tickets_completed > (
            SELECT COALESCE(tickets_completed, 0)
            FROM mm_stats
            WHERE user_id = %s
        )
    """, (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result['rank'] if result else None

def can_access_tier(user_roles, ticket_tier):
    """Check if user can access this ticket tier"""
    mm_role_ids = get_all_mm_roles()
    user_role_ids = [role.id for role in user_roles]
    
    ticket_level = MM_TIERS[ticket_tier]['level']
    
    for tier_key, role_id in mm_role_ids.items():
        if role_id in user_role_ids:
            user_level = MM_TIERS[tier_key]['level']
            # 250+ can see everything, others only their level and below
            if tier_key == '250_plus' or user_level >= ticket_level:
                return True
    
    return False

def is_mm_or_staff(user):
    """Check if user is MM or staff"""
    if user.guild_permissions.administrator:
        return True
    
    mm_role_ids = get_all_mm_roles()
    staff_role_id = get_config('staff_role')
    
    user_role_ids = [role.id for role in user.roles]
    
    if staff_role_id and int(staff_role_id) in user_role_ids:
        return True
    
    for role_id in mm_role_ids.values():
        if role_id in user_role_ids:
            return True
    
    return False

# This is Part 3 - Modals (Pop-up forms for creating tickets)

class MMTradeModal(Modal, title='Middleman Trade Details'):
    def __init__(self, tier):
        super().__init__()
        self.tier = tier

        self.trader = TextInput(
            label='Who are you trading with?',
            placeholder='@username or Discord ID',
            required=True,
            max_length=100
        )

        self.giving = TextInput(
            label='What are you giving?',
            placeholder='Example: 100 Robux, Blox Fruits items, etc.',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.receiving = TextInput(
            label='What is the other trader giving?',
            placeholder='Example: $50 PayPal, Discord Nitro, etc.',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.both_join = TextInput(
            label='Can both users join Discord calls?',
            placeholder='YES or NO',
            required=True,
            max_length=10
        )

        self.tip = TextInput(
            label='Will you tip the middleman?',
            placeholder='Optional - helps support our team!',
            required=False,
            max_length=200
        )

        self.add_item(self.trader)
        self.add_item(self.giving)
        self.add_item(self.receiving)
        self.add_item(self.both_join)
        self.add_item(self.tip)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            await create_mm_ticket(
                interaction.guild, 
                interaction.user, 
                self.tier,
                self.trader.value,
                self.giving.value,
                self.receiving.value,
                self.both_join.value,
                self.tip.value if self.tip.value else 'None'
            )
            await interaction.followup.send('✅ Your middleman ticket has been created! Check the new channel.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error creating ticket: {str(e)}', ephemeral=True)

class SupportTicketModal(Modal, title='Open Support Ticket'):
    def __init__(self):
        super().__init__()

        self.reason = TextInput(
            label='Reason for Support',
            placeholder='Example: Need help, report issue, partnership, etc.',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )

        self.details = TextInput(
            label='Additional Details',# This is Part 4 - Views, Buttons, and Dropdowns

class MMSetupView(View):
    """The persistent view for MM setup panel"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open MM Ticket', emoji='⚖️', style=discord.ButtonStyle.primary, custom_id='open_mm_ticket_main')
    async def open_mm_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title='Select your middleman tier',
            description='Choose the tier that matches your trade value',
            color=MM_COLOR
        )
        await interaction.response.send_message(embed=embed, view=TierSelectView(), ephemeral=True)

class SupportSetupView(View):
    """The persistent view for support panel"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open Support Ticket', emoji='🎫', style=discord.ButtonStyle.primary, custom_id='open_support_ticket_main')
    async def open_support_button(self, interaction: discord.Interaction, button: Button):
        modal = SupportTicketModal()
        await interaction.response.send_modal(modal)

class TierSelect(Select):
    """Dropdown to select MM tier"""
    def __init__(self):
        options = [
            discord.SelectOption(
                label='$1-$50 Middleman',
                description='Small trades and items',
                value='1_50',
                emoji='🟢'
            ),
            discord.SelectOption(
                label='$50-$100 Middleman',
                description='Medium value trades',
                value='50_100',
                emoji='🔵'
            ),
            discord.SelectOption(
                label='$100-$250 Middleman',
                description='High value trades',
                value='100_250',
                emoji='🟣'
            ),
            discord.SelectOption(
                label='$250+ Middleman',
                description='Premium and exclusive trades',
                value='250_plus',
                emoji='💎'
            )
        ]
        
        super().__init__(
            placeholder='Select tier based on your trade value',
            options=options,
            custom_id='tier_select'
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_tier = self.values[0]
        modal = MMTradeModal(selected_tier)
        await interaction.response.send_modal(modal)

class TierSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TierSelect())

class MMTicketView(View):
    """Buttons inside MM tickets"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='✅ Claim Ticket', style=discord.ButtonStyle.success, custom_id='claim_mm_ticket')
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        ticket = get_ticket_db(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message('❌ Ticket data not found!', ephemeral=True)
        
        if not can_access_tier(interaction.user.roles, ticket['tier']) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message('❌ You do not have permission to claim this tier!', ephemeral=True)
        
        if ticket['claimed_by']:
            claimer = interaction.guild.get_member(ticket['claimed_by'])
            return await interaction.response.send_message(f'❌ Already claimed by {claimer.mention if claimer else "someone"}!', ephemeral=True)
        
        claim_ticket_db(interaction.channel.id, interaction.user.id)
        
        ticket_creator = interaction.guild.get_member(ticket['user_id']) if ticket['user_id'] else None
        
        # Lock channel to only claimer and creator
        await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)
        
        if ticket_creator:
            await interaction.channel.set_permissions(ticket_creator, view_channel=True, send_messages=True, read_message_history=True)
        
        embed = discord.Embed(
            description=f'✅ Ticket claimed by {interaction.user.mention}\n\n🔒 **Only the claimer and ticket creator can talk now.**',
            color=SUCCESS_COLOR
        )
        embed.timestamp = datetime.utcnow()
        
        await interaction.response.send_message(embed=embed)
        await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
    
    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_mm_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

class SupportTicketView(View):
    """Buttons inside support tickets"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_support_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)
            placeholder='Provide any extra information that might help us...',
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000
        )

        self.add_item(self.reason)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            await create_support_ticket(
                interaction.guild, 
                interaction.user,
                self.reason.value,
                self.details.value if self.details.value else 'None provided'
            )
            await interaction.followup.send('✅ Support ticket created! Check the new channel.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error creating ticket: {str(e)}', ephemeral=True)

      # This is Part 5 - Coinflip System (KEPT AS-IS per your request)

class CoinflipView(View):
    def __init__(self, user1, user2, total_rounds, is_first_to):
        super().__init__(timeout=60)
        self.user1 = user1
        self.user2 = user2
        self.total_rounds = total_rounds
        self.is_first_to = is_first_to
        self.user1_choice = None
        self.user2_choice = None
        self.chosen_users = []
    
    @discord.ui.button(label='Heads', emoji='🪙', style=discord.ButtonStyle.primary, custom_id='heads_cf')
    async def heads_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.user1.id, self.user2.id]:
            return await interaction.response.send_message('❌ You are not part of this coinflip!', ephemeral=True)
        
        if interaction.user.id in self.chosen_users:
            return await interaction.response.send_message('❌ You already made your choice!', ephemeral=True)
        
        if interaction.user.id == self.user1.id:
            self.user1_choice = 'heads'
        else:
            self.user2_choice = 'heads'
        
        self.chosen_users.append(interaction.user.id)
        button.disabled = True
        
        mode_text = f"First to {self.total_rounds}" if self.is_first_to else f"Best of {self.total_rounds}"
        embed = discord.Embed(
            title='🪙 Choose Your Side',
            description=f'**{self.user1.mention}** vs **{self.user2.mention}**\n\n**Mode:** {mode_text}\n\n**Select your side below:**',
            color=MM_COLOR
        )
        
        if self.user1_choice:
            embed.add_field(name=f'{self.user1.display_name} has chosen', value=f'**{self.user1_choice.upper()}**', inline=False)
        if self.user2_choice:
            embed.add_field(name=f'{self.user2.display_name} has chosen', value=f'**{self.user2_choice.upper()}**', inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        if len(self.chosen_users) == 2:
            await asyncio.sleep(1)
            await self.start_coinflip(interaction)
    
    @discord.ui.button(label='Tails', emoji='🪙', style=discord.ButtonStyle.secondary, custom_id='tails_cf')
    async def tails_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.user1.id, self.user2.id]:
            return await interaction.response.send_message('❌ You are not part of this coinflip!', ephemeral=True)
        
        if interaction.user.id in self.chosen_users:
            return await interaction.response.send_message('❌ You already made your choice!', ephemeral=True)
        
        if interaction.user.id == self.user1.id:
            self.user1_choice = 'tails'
        else:
            self.user2_choice = 'tails'
        
        self.chosen_users.append(interaction.user.id)
        button.disabled = True
        
        mode_text = f"First to {self.total_rounds}" if self.is_first_to else f"Best of {self.total_rounds}"
        embed = discord.Embed(
            title='🪙 Choose Your Side',
            description=f'**{self.user1.mention}** vs **{self.user2.mention}**\n\n**Mode:** {mode_text}\n\n**Select your side below:**',
            color=MM_COLOR
        )
        
        if self.user1_choice:
            embed.add_field(name=f'{self.user1.display_name} has chosen', value=f'**{self.user1_choice.upper()}**', inline=False)
        if self.user2_choice:
            embed.add_field(name=f'{self.user2.display_name} has chosen', value=f'**{self.user2_choice.upper()}**', inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        if len(self.chosen_users) == 2:
            await asyncio.sleep(1)
            await self.start_coinflip(interaction)
    
    async def start_coinflip(self, interaction):
        for item in self.children:
            item.disabled = True
        
        mode_text = f"First to {self.total_rounds}" if self.is_first_to else f"Best of {self.total_rounds}"
        
        start_embed = discord.Embed(
            title='🪙 Coinflip Starting!',
            description=f'**{self.user1.mention}** chose **{self.user1_choice.upper()}**\n**{self.user2.mention}** chose **{self.user2_choice.upper()}**\n\n**Mode:** {mode_text}',
            color=MM_COLOR
        )
        start_embed.timestamp = datetime.utcnow()
        
        await interaction.message.edit(embed=start_embed, view=self)
        await asyncio.sleep(2)
        
        user1_wins = 0
        user2_wins = 0
        rounds_played = 0
        results = []
        last_winner = None
        streak_count = 0
        
        if self.is_first_to:
            while user1_wins < self.total_rounds and user2_wins < self.total_rounds:
                if streak_count >= 3:
                    rand_num = secrets.randbelow(100)
                    if last_winner == 'user1':
                        flip_result = self.user2_choice if rand_num < 60 else self.user1_choice
                    else:
                        flip_result = self.user1_choice if rand_num < 60 else self.user2_choice
                else:
                    flip_result = 'heads' if secrets.randbelow(2) == 0 else 'tails'
                
                rounds_played += 1
                
                if flip_result == self.user1_choice:
                    user1_wins += 1
                    results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user1.mention} wins! 🎉")
                    if last_winner == 'user1':
                        streak_count += 1
                    else:
                        streak_count = 1
                        last_winner = 'user1'
                else:
                    user2_wins += 1
                    results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user2.mention} wins! 🎉")
                    if last_winner == 'user2':
                        streak_count += 1
                    else:
                        streak_count = 1
                        last_winner = 'user2'
                
                progress_embed = discord.Embed(
                    title='🪙 Coinflip in Progress...',
                    description=f'**{self.user1.mention}** ({self.user1_choice.upper()}): {user1_wins} wins\n**{self.user2.mention}** ({self.user2_choice.upper()}): {user2_wins} wins\n\n**Mode:** {mode_text}\n**Rounds Played:** {rounds_played}',
                    color=0xFFA500
                )
                
                recent_results = '\n'.join(results[-5:])
                progress_embed.add_field(name='Recent Results', value=recent_results if recent_results else 'None yet', inline=False)
                progress_embed.timestamp = datetime.utcnow()
                
                await interaction.message.edit(embed=progress_embed, view=self)
                await asyncio.sleep(1.5)
        else:
            rounds_to_win = (self.total_rounds // 2) + 1
            
            while rounds_played < self.total_rounds:
                if streak_count >= 3:
                    rand_num = secrets.randbelow(100)
                    if last_winner == 'user1':
                        flip_result = self.user2_choice if rand_num < 60 else self.user1_choice
                    else:
                        flip_result = self.user1_choice if rand_num < 60 else self.user2_choice
                else:
                    flip_result = 'heads' if secrets.randbelow(2) == 0 else 'tails'
                
                rounds_played += 1
                
                if flip_result == self.user1_choice:
                    user1_wins += 1
                    results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user1.mention} wins! 🎉")
                    if last_winner == 'user1':
                        streak_count += 1
                    else:
                        streak_count = 1
                        last_winner = 'user1'
                else:
                    user2_wins += 1
                    results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user2.mention} wins! 🎉")
                    if last_winner == 'user2':
                        streak_count += 1
                    else:
                        streak_count = 1
                        last_winner = 'user2'
                
                if user1_wins >= rounds_to_win or user2_wins >= rounds_to_win:
                    break
                
                progress_embed = discord.Embed(
                    title='🪙 Coinflip in Progress...',
                    description=f'**{self.user1.mention}** ({self.user1_choice.upper()}): {user1_wins} wins\n**{self.user2.mention}** ({self.user2_choice.upper()}): {user2_wins} wins\n\n**Mode:** {mode_text}\n**Rounds Played:** {rounds_played}/{self.total_rounds}',
                    color=0xFFA500
                )
                
                recent_results = '\n'.join(results[-5:])
                progress_embed.add_field(name='Recent Results', value=recent_results if recent_results else 'None yet', inline=False)
                progress_embed.timestamp = datetime.utcnow()
                
                await interaction.message.edit(embed=progress_embed, view=self)
                await asyncio.sleep(1.5)
        
        if user1_wins > user2_wins:
            final_winner = self.user1
            final_color = 0x57F287
        elif user2_wins > user1_wins:
            final_winner = self.user2
            final_color = 0x57F287
        else:
            final_winner = None
            final_color = 0xFEE75C
        
        final_embed = discord.Embed(
            title='🪙 Coinflip Complete!',
            color=final_color
        )
        
        if final_winner:
            final_embed.description = f'🎊 **{final_winner.mention} WINS!** 🎊\n\n**Final Score:**\n{self.user1.mention}: {user1_wins} wins\n{self.user2.mention}: {user2_wins} wins'
        else:
            final_embed.description = f'🤝 **IT\'S A TIE!** 🤝\n\n**Final Score:**\n{self.user1.mention}: {user1_wins} wins\n{self.user2.mention}: {user2_wins} wins'
        
        final_embed.add_field(name='Mode', value=mode_text, inline=True)
        final_embed.add_field(name='Total Rounds', value=str(rounds_played), inline=True)
        
        if rounds_played <= 10:
            all_results = '\n'.join(results)
            final_embed.add_field(name='All Results', value=all_results, inline=False)
        else:
            recent_results = '\n'.join(results[-10:])
            final_embed.add_field(name='Last 10 Results', value=recent_results, inline=False)
        
        await interaction.message.edit(embed=final_embed, view=self)

  # This is Part 6 - All Bot Commands, Events, and Helper Functions

@bot.event
async def on_ready():
    print(f'✅ Bot online as {bot.user}')
    print(f'📊 Serving {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='trades'))
    
    # Register persistent views
    bot.add_view(TierSelectView())
    bot.add_view(MMTicketView())
    bot.add_view(SupportTicketView())
    bot.add_view(MMSetupView())
    bot.add_view(SupportSetupView())

# Setup Commands
@bot.command(name='mmsetup')
@commands.has_permissions(administrator=True)
async def mmsetup(ctx):
    """Create MM ticket panel"""
    embed = discord.Embed(
        title='⚖️ Middleman Services',
        description='Need a secure middleman for your trade? Open a ticket below!\n\n**Available Tiers:**\n🟢 **$1-$50** - Small trades and items\n🔵 **$50-$100** - Medium value trades\n🟣 **$100-$250** - High value trades\n💎 **$250+** - Premium and exclusive trades',
        color=MM_COLOR
    )
    embed.set_footer(text='Select your tier to get started')
    
    await ctx.send(embed=embed, view=MMSetupView())
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='supportsetup')
@commands.has_permissions(administrator=True)
async def supportsetup(ctx):
    """Create Support ticket panel"""
    embed = discord.Embed(
        title='🎫 Support Center',
        description='Need help? Open a support ticket!\n\n**What we can help with:**\n• General Support\n• Prize Claims\n• Partnerships\n• Reporting Issues\n• Questions',
        color=MM_COLOR
    )
    embed.set_footer(text='Click below to open a ticket')
    embed.timestamp = datetime.utcnow()
    
    await ctx.send(embed=embed, view=SupportSetupView())
    try:
        await ctx.message.delete()
    except:
        pass

# Configuration Commands
@bot.command(name='setrole')
@commands.has_permissions(administrator=True)
async def setrole(ctx, tier: str, role: discord.Role):
    """Set MM role for a tier: $setrole 1_50 @role"""
    valid_tiers = ['1_50', '50_100', '100_250', '250_plus', 'staff', 'mm_team']
    
    if tier not in valid_tiers:
        return await ctx.reply(f'❌ Invalid tier! Use: {", ".join(valid_tiers)}')
    
    set_config(f'mm_role_{tier}' if tier not in ['staff', 'mm_team'] else tier + '_role', role.id)
    await ctx.reply(f'✅ Set **{tier}** role to {role.mention}')

@bot.command(name='setproof')
@commands.has_permissions(administrator=True)
async def setproof(ctx, channel: discord.TextChannel):
    """Set proof channel: $setproof #channel"""
    set_config('proof_channel', channel.id)
    await ctx.reply(f'✅ Proof channel set to {channel.mention}')

# Ticket Commands
@bot.command(name='claim')
async def claim(ctx):
    """Claim a ticket"""
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ You do not have permission to use this!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')

    ticket = get_ticket_db(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ Ticket data not found!')
    
    if ticket['claimed_by']:
        return await ctx.reply('❌ This ticket is already claimed!')
    
    if not can_access_tier(ctx.author.roles, ticket['tier']) and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ You cannot claim this tier!')

    claim_ticket_db(ctx.channel.id, ctx.author.id)
    
    ticket_creator = ctx.guild.get_member(ticket['user_id'])
    
    await ctx.channel.set_permissions(ctx.author, view_channel=True, send_messages=True, read_message_history=True)
    
    if ticket_creator:
        await ctx.channel.set_permissions(ticket_creator, view_channel=True, send_messages=True, read_message_history=True)
    
    embed = discord.Embed(
        description=f'✅ Ticket claimed by {ctx.author.mention}\n\n🔒 **Only the claimer and ticket creator can talk now.**',
        color=SUCCESS_COLOR
    )
    embed.timestamp = datetime.utcnow()

    await ctx.send(embed=embed)
    await ctx.channel.edit(name=f"{ctx.channel.name}-claimed")

@bot.command(name='unclaim')
async def unclaim(ctx):
    """Unclaim a ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')
    
    ticket = get_ticket_db(ctx.channel.id)
    if not ticket or not ticket['claimed_by']:
        return await ctx.reply('❌ This ticket is not claimed!')
    
    if ctx.author.id != ticket['claimed_by'] and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ Only the claimer or admin can unclaim!')
    
    unclaim_ticket_db(ctx.channel.id)
    
    # Restore permissions
    mm_role_ids = get_all_mm_roles()
    ticket_level = MM_TIERS[ticket['tier']]['level']
    
    for tier_key, role_id in mm_role_ids.items():
        role = ctx.guild.get_role(role_id)
        if role:
            tier_level = MM_TIERS[tier_key]['level']
            if tier_key == '250_plus' or tier_level >= ticket_level:
                await ctx.channel.set_permissions(role, view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    
    new_name = ctx.channel.name.replace('-claimed', '')
    await ctx.channel.edit(name=new_name)
    
    embed = discord.Embed(
        description=f'✅ Ticket unclaimed by {ctx.author.mention}\n\n🔓 **All eligible middlemen can now claim this again.**',
        color=MM_COLOR
    )
    
    await ctx.reply(embed=embed)

@bot.command(name='close')
async def close_cmd(ctx):
    """Close a ticket"""
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ You do not have permission!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')

    embed = discord.Embed(
        title='⚠️ Close Ticket',
        description='Are you sure you want to close this ticket?',
        color=ERROR_COLOR
    )
    embed.set_footer(text='This action cannot be undone')

    view = View(timeout=60)
    
    confirm_button = Button(label='Confirm', style=discord.ButtonStyle.danger)
    cancel_button = Button(label='Cancel', style=discord.ButtonStyle.secondary)
    
    async def confirm_callback(interaction):
        await interaction.response.defer()
        await close_ticket(ctx.channel, ctx.author)
    
    async def cancel_callback(interaction):
        await interaction.response.edit_message(content='❌ Cancelled.', embed=None, view=None)
    
    confirm_button.callback = confirm_callback
    cancel_button.callback = cancel_callback
    
    view.add_item(confirm_button)
    view.add_item(cancel_button)

    await ctx.reply(embed=embed, view=view)

@bot.command(name='add')
async def add_user(ctx, member: discord.Member = None):
    """Add user to ticket"""
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ You do not have permission!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been added to the ticket',
        color=SUCCESS_COLOR
    )
    embed.timestamp = datetime.utcnow()

    await ctx.reply(embed=embed)

@bot.command(name='remove')
async def remove_user(ctx, member: discord.Member = None):
    """Remove user from ticket"""
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ You do not have permission!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been removed from the ticket',
        color=SUCCESS_COLOR
    )
    embed.timestamp = datetime.utcnow()

    await ctx.reply(embed=embed)

@bot.command(name='proof')
async def proof_cmd(ctx):
    """Send MM proof to proof channel"""
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ You do not have permission!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This only works in ticket channels!')

    ticket = get_ticket_db(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ No ticket data found.')

    proof_channel_id = get_config('proof_channel')
    if not proof_channel_id or proof_channel_id == '0':
        return await ctx.reply('❌ Proof channel not configured! Use `$setproof #channel`')

    proof_channel = ctx.guild.get_channel(int(proof_channel_id))
    if not proof_channel:
        return await ctx.reply('❌ Proof channel not found.')

    requester = ctx.guild.get_member(ticket['user_id'])

    embed = discord.Embed(
        title='✅ Trade Completed',
        color=SUCCESS_COLOR
    )

    embed.add_field(name='Middleman', value=ctx.author.mention, inline=False)
    embed.add_field(name='Tier', value=MM_TIERS[ticket['tier']]['name'], inline=False)
    embed.add_field(name='Requester', value=requester.mention if requester else 'Unknown', inline=False)
    embed.add_field(name='Trader', value=ticket.get('trader', 'Unknown'), inline=False)
    embed.add_field(name='Gave', value=ticket.get('giving', 'Unknown'), inline=False)
    embed.add_field(name='Received', value=ticket.get('receiving', 'Unknown'), inline=False)

    ticket_number = ctx.channel.name.replace('ticket-', '').replace('-claimed', '')
    embed.set_footer(text=f"Ticket #{ticket_number}")
    embed.timestamp = datetime.utcnow()

    await proof_channel.send(embed=embed)
    
    increment_mm_stats(ctx.author.id)
    
    await ctx.reply('✅ Proof sent successfully!')

# Stats Commands
@bot.command(name='mmstats')
async def mmstats_cmd(ctx, member: discord.Member = None):
    """View MM statistics"""
    target = member if member else ctx.author
    
    stats = get_mm_stats(target.id)
    rank = get_mm_rank(target.id)
    
    embed = discord.Embed(
        title=f'📊 Middleman Statistics',
        description=f'Statistics for {target.mention}',
        color=MM_COLOR
    )
    
    embed.add_field(
        name='✅ Tickets Completed',
        value=f'**{stats["tickets_completed"]}** tickets',
        inline=False
    )
    
    if rank:
        total_mms = len(get_mm_leaderboard(1000))
        embed.add_field(
            name='🏆 Rank',
            value=f'#{rank} out of {total_mms} middlemen',
            inline=False
        )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    
    await ctx.reply(embed=embed)

@bot.command(name='mmleaderboard')
async def mmleaderboard_cmd(ctx):
    """View top middlemen"""
    leaderboard = get_mm_leaderboard(10)
    
    if not leaderboard:
        return await ctx.reply('❌ No statistics available yet!')
    
    embed = discord.Embed(
        title='🏆 Middleman Leaderboard',
        description='Top middlemen by completed tickets',
        color=MM_COLOR
    )
    
    leaderboard_text = []
    for i, entry in enumerate(leaderboard, 1):
        member = ctx.guild.get_member(entry['user_id'])
        if member:
            medal = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            leaderboard_text.append(f'{medal} {member.mention} - **{entry["tickets_completed"]}** tickets')
    
    if leaderboard_text:
        embed.description = '\n'.join(leaderboard_text)
    else:
        embed.description = 'No data available'
    
    embed.set_footer(text=f'Total Middlemen: {len(leaderboard)}')
    
    await ctx.reply(embed=embed)

# Coinflip Commands (KEPT AS-IS)
@bot.command(name='coinflip')
async def simple_coinflip(ctx):
    """Flip a single coin"""
    embed = discord.Embed(
        title='🪙 Flipping Coin...',
        description='The coin is in the air!',
        color=MM_COLOR
    )
    
    msg = await ctx.reply(embed=embed)
    await asyncio.sleep(1.5)
    
    result = 'Heads' if secrets.randbelow(2) == 0 else 'Tails'
    
    result_embed = discord.Embed(
        title=f'🪙 {result}!',
        description=f'The coin landed on **{result}**!',
        color=SUCCESS_COLOR if result == 'Heads' else MM_COLOR
    )
    result_embed.set_footer(text=f'Flipped by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
    
    await msg.edit(embed=result_embed)

@bot.command(name='cf')
async def coinflip(ctx, user1_input: str = None, vs: str = None, user2_input: str = None, mode: str = None, rounds: int = None):
    """Coinflip: $cf @user1 vs @user2 ft 3"""
    if not all([user1_input, vs, user2_input]):
        return await ctx.reply('❌ Usage: `$cf @user1 vs @user2 [ft/bo] <number>`\nExample: `$cf @user1 vs @user2 ft 3`')
    
    if vs.lower() != 'vs':
        return await ctx.reply('❌ Please use "vs" between usernames!')
    
    user1 = None
    user2 = None
    
    if user1_input.startswith('<@'):
        try:
            user_id = int(user1_input.strip('<@!>'))
            user1 = ctx.guild.get_member(user_id)
        except:
            pass
    else:
        user1 = discord.utils.find(lambda m: m.name.lower() == user1_input.lower() or (m.nick and m.nick.lower() == user1_input.lower()), ctx.guild.members)
    
    if user2_input.startswith('<@'):
        try:
            user_id = int(user2_input.strip('<@!>'))
            user2 = ctx.guild.get_member(user_id)
        except:
            pass
    else:
        user2 = discord.utils.find(lambda m: m.name.lower() == user2_input.lower() or (m.nick and m.nick.lower() == user2_input.lower()), ctx.guild.members)
    
    if not user1:
        return await ctx.reply(f'❌ Could not find user: {user1_input}')
    if not user2:
        return await ctx.reply(f'❌ Could not find user: {user2_input}')
    
    is_first_to = False
    total_rounds = 1
    
    if mode:
        if mode.lower() in ['ft', 'firstto']:
            if rounds is None:
                return await ctx.reply('❌ Specify rounds for "ft" mode!\nExample: `$cf @user1 vs @user2 ft 3`')
            is_first_to = True
            total_rounds = rounds
        elif mode.lower() in ['bo', 'bestof']:
            if rounds is None:
                return await ctx.reply('❌ Specify rounds for "bo" mode!\nExample: `$cf @user1 vs @user2 bo 5`')
            is_first_to = False
            total_rounds = rounds
        elif mode.isdigit():
            total_rounds = int(mode)
            is_first_to = False
        else:
            return await ctx.reply('❌ Invalid mode! Use "ft" or "bo".')
    
    if total_rounds < 1 or total_rounds > 200:
        return await ctx.reply('❌ Rounds must be between 1 and 200!')
    
    mode_text = f"First to {total_rounds}" if is_first_to else f"Best of {total_rounds}"
    
    embed = discord.Embed(
        title='🪙 Choose Your Side',
        description=f'**{user1.mention}** vs **{user2.mention}**\n\n**Mode:** {mode_text}\n\n**Select your side below:**',
        color=MM_COLOR
    )
    
    view = CoinflipView(user1, user2, total_rounds, is_first_to)
    await ctx.send(embed=embed, view=view)

# Clean Command
@bot.command(name='clean')
@commands.has_permissions(manage_messages=True)
async def clean_cmd(ctx, amount: int = 100):
    """Delete bot messages: $clean [amount]"""
    deleted = 0
    async for message in ctx.channel.history(limit=amount):
        if message.author == bot.user:
            try:
                await message.delete()
                deleted += 1
            except:
                pass
    
    msg = await ctx.send(f'✅ Cleaned {deleted} bot messages!')
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except:
        pass

# Updated Help Command
@bot.command(name='help')
async def help_cmd(ctx):
    """Show all commands"""
    embed = discord.Embed(
        title='📋 Bot Commands',
        description='Here\'s everything you can do:',
        color=MM_COLOR
    )
    
    embed.add_field(
        name='🎫 Ticket Commands',
        value='`$mmsetup` - Create MM ticket panel\n'
              '`$supportsetup` - Create support panel\n'
              '`$claim` - Claim a ticket\n'
              '`$unclaim` - Unclaim a ticket\n'
              '`$close` - Close a ticket\n'
              '`$add @user` - Add user to ticket\n'
              '`$remove @user` - Remove user from ticket\n'
              '`$proof` - Send completion proof',
        inline=False
    )
    
    embed.add_field(
        name='⚙️ Setup Commands',
        value='`$setrole <tier> @role` - Set MM role\n'
              '`$setproof #channel` - Set proof channel\n'
              'Tiers: `1_50`, `50_100`, `100_250`, `250_plus`, `staff`, `mm_team`',
        inline=False
    )
    
    embed.add_field(
        name='📊 Statistics',
        value='`$mmstats [@user]` - View MM stats\n'
              '`$mmleaderboard` - Top middlemen',
        inline=False
    )
    
    embed.add_field(
        name='🪙 Coinflip',
        value='`$coinflip` - Flip a single coin\n'
              '`$cf @user1 vs @user2 ft <#>` - First to X wins\n'
              '`$cf @user1 vs @user2 bo <#>` - Best of X rounds',
        inline=False
    )
    
    embed.add_field(
        name='🧹 Utility',
        value='`$clean [amount]` - Delete bot messages',
        inline=False
    )
    
    embed.set_footer(text='Need help? Open a support ticket!')
    
    await ctx.reply(embed=embed)

# Helper Functions
async def create_mm_ticket(guild, user, tier, trader, giving, receiving, both_join, tip):
    """Create MM ticket"""
    try:
        category = discord.utils.get(guild.categories, name='MM Tickets')
        if not category:
            category = await guild.create_category('MM Tickets')
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        
        # Add MM roles that can see this tier
        mm_role_ids = get_all_mm_roles()
        ticket_level = MM_TIERS[tier]['level']
        
        mm_team_role_id = get_config('mm_team_role')
        if mm_team_role_id and mm_team_role_id != '0':
            mm_team_role = guild.get_role(int(mm_team_role_id))
            if mm_team_role:
                overwrites[mm_team_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        
        for tier_key, role_id in mm_role_ids.items():
            role = guild.get_role(role_id)
            if role:
                tier_level = MM_TIERS[tier_key]['level']
                if tier_key == '250_plus' or tier_level >= ticket_level:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        
        ticket_channel = await guild.create_text_channel(
            name=f'ticket-{user.name}-mm',
            category=category,
            overwrites=overwrites
        )
        
        create_ticket_db(ticket_channel.id, user.id, 'mm', tier=tier, trader=trader, giving=giving, receiving=receiving, both_join=both_join, tip=tip)
         ticket_channel.send(f'{mm_team_role.mention} {user.mention}')
        
          # Ping MM team role (configurable)
        if mm_team_role_id and mm_team_role_id != '0':
            mm_team_role = guild.get_role(int(mm_team_role_id))
            if mm_team_role:
                await ticket_channel.send(f'{mm_team_role.mention} {user.mention}')
        
        embed = discord.Embed(
            title=f"{MM_TIERS[tier]['emoji']} {MM_TIERS[tier]['name']}",
            description=f"Welcome {user.mention}!\n\nA middleman will be with you shortly.",
            color=MM_COLOR
        )
        
        embed.add_field(name="📊 Trade Details", value=f"**Range:** {MM_TIERS[tier]['range']}\n**Status:** 🟡 Waiting", inline=False)
        embed.add_field(name="👥 Trading With", value=trader, inline=False)
        embed.add_field(name="📤 You're Giving", value=giving, inline=True)
        embed.add_field(name="📥 You're Receiving", value=receiving, inline=True)
        embed.add_field(name="🔗 Both Can Join Calls?", value=both_join, inline=True)
        embed.add_field(name="💰 Tip", value=tip if tip else "None", inline=True)
        
        embed.set_footer(text=f'Ticket created by {user.name}', icon_url=user.display_avatar.url)
        embed.timestamp = datetime.utcnow()
        
        await ticket_channel.send(embed=embed, view=MMTicketView()
    except Exception as e:
        print(f'[ERROR] MM Ticket creation failed: {e}')
        raise

async def create_support_ticket(guild, user, reason, details):
    """Create support ticket"""
    try:
        category = discord.utils.get(guild.categories, name='Support Tickets')
        if not category:
            category = await guild.create_category('Support Tickets')
        
        staff_role_id = get_config('staff_role')
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id and staff_role_id != '0' else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        
        ticket_channel = await guild.create_text_channel(
            name=f'ticket-{user.name}-support',
            category=category,
            overwrites=overwrites
        )
        
        create_ticket_db(ticket_channel.id, user.id, 'support', reason=reason, details=details)
        
        if staff_role:
            await ticket_channel.send(f'{staff_role.mention} {user.mention}')
        
        embed = discord.Embed(
            title='🎫 Support Ticket',
            description=f"Welcome {user.mention}!\n\nOur staff will help you shortly.",
            color=MM_COLOR
        )
        
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.add_field(name="📝 Details", value=details, inline=False)
        
        embed.set_footer(text=f'Ticket created by {user.name}', icon_url=user.display_avatar.url)
        embed.timestamp = datetime.utcnow()
        
        await ticket_channel.send(embed=embed, view=SupportTicketView())
        
    except Exception as e:
        print(f'[ERROR] Support Ticket creation failed: {e}')
        raise

async def close_ticket(channel, user):
    """Close ticket"""
    embed = discord.Embed(
        title='🔒 Ticket Closed',
        description=f'Ticket closed by {user.mention}',
        color=ERROR_COLOR
    )
    embed.timestamp = datetime.utcnow()

    await channel.send(embed=embed)

    delete_ticket_db(channel.id)

    await asyncio.sleep(5)
    await channel.delete()

# Run Bot
if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print('❌ ERROR: No TOKEN found!')
    else:
        print('🚀 Starting bot...')
        bot.run(TOKEN)
