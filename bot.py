import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
import os
import secrets
from datetime import datetime
import asyncio
from flask import Flask
from threading import Thread
import psycopg2  
from psycopg2.extras import RealDictCursor  
from dotenv import load_dotenv  

load_dotenv()  # NEW: Load .env file

# Keep bot alive
app = Flask('')

@app.route('/')
def home():
    return "<h1 style='text-align:center; margin-top:50px; font-family:Arial;'>Bot is Active</h1>"

def run():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot Configuration
PREFIX = '$'
DATABASE_URL = os.getenv('DATABASE_URL')
TICKET_CATEGORY = 'MM Tickets'
PROOF_CHANNEL_ID = 1472858074086768774  # CHANGE THIS TO YOUR PROOF CHANNEL ID

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Color
MM_COLOR = 0xFEE75C

# MM Tier definitions with hierarchy
MM_TIERS = {
    'basic': {
        'name': '$1-$15 Middleman',
        'range': '$1-$15 Worth of Stuff',
        'emoji': '💲',
        'level': 1
    },
    'advanced': {
        'name': '$15-$50 Middleman',
        'range': '$15-$50 Worth of Stuff',
        'emoji': '💸',
        'level': 2
    },
    'premium': {
        'name': '$50-$150 Middleman',
        'range': '$50-$150 Worth of Stuff',
        'emoji': '💰',
        'level': 3
    },
    'og': {
        'name': '$150+ Middleman',
        'range': '$150+ Worth of Stuff',
        'emoji': '💳',
        'level': 4
    }
}

# MM Role IDs - UPDATE THESE WITH YOUR ROLE IDS
MM_ROLE_IDS = {
    "basic": 1427769765484695666,        # 0-150M role ID
    "advanced": 1424908470075003032,     # 150-500M role ID
    "premium": 1426475143924027393,      # 500M+ role ID
    "og": 1425251754584309905         # OG MM role ID
}

SUPPORT_CATEGORY = 'Support Tickets'
STAFF_ROLE_ID = 1407252499760680960


def init_database():
    """Creates database tables when bot starts"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Create tickets table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                ticket_type VARCHAR(50) NOT NULL,
                tier VARCHAR(50),
                trader TEXT,
                giving TEXT,
                receiving TEXT,
                tip TEXT,
                reason TEXT,
                details TEXT,
                claimed_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create mm_stats table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mm_stats (
                user_id BIGINT PRIMARY KEY,
                tickets_completed INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database tables ready")
    except Exception as e:
        print(f"❌ Database error: {e}")

def get_db():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL)

def save_ticket(channel_id, user_id, ticket_type, **kwargs):
    """Save a ticket to database"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (channel_id, user_id, ticket_type, tier, trader, giving, receiving, tip, reason, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        channel_id, user_id, ticket_type,
        kwargs.get('tier'), kwargs.get('trader'), kwargs.get('giving'),
        kwargs.get('receiving'), kwargs.get('tip'),
        kwargs.get('reason'), kwargs.get('details')
    ))
    conn.commit()
    cur.close()
    conn.close()

def get_ticket(channel_id):
    """Get ticket data from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tickets WHERE channel_id = %s", (channel_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result

def claim_ticket_db(channel_id, user_id):
    """Mark ticket as claimed"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = %s WHERE channel_id = %s", (user_id, channel_id))
    conn.commit()
    cur.close()
    conn.close()

def unclaim_ticket_db(channel_id):
    """Remove claim from ticket"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = NULL WHERE channel_id = %s", (channel_id,))
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
    """Add 1 to MM's completed tickets"""
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

def get_mm_stats_db(user_id):
    """Get MM statistics from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM mm_stats WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result if result else {'user_id': user_id, 'tickets_completed': 0}

def get_mm_leaderboard_db(limit=10):
    """Get top MMs from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id, tickets_completed FROM mm_stats ORDER BY tickets_completed DESC LIMIT %s", (limit,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def can_see_tier(user_roles, ticket_tier):
    """Check if user with their roles can see a ticket of given tier"""
    user_role_ids = [role.id for role in user_roles]
    ticket_level = MM_TIERS[ticket_tier]['level']

def is_mm_or_admin(user, guild):
    """Check if user is MM or admin"""
    # Check if admin
    if user.guild_permissions.administrator:
        return True
    
    # Check if user has any MM role
    user_role_ids = [role.id for role in user.roles]
    for role_id in MM_ROLE_IDS.values():
        if role_id in user_role_ids:
            return True
    
    return False
    
    # OG can see everything
    if MM_ROLE_IDS['og'] in user_role_ids:
        return True
    
    # Check if user has a role that matches or exceeds the ticket tier
    for tier_key, role_id in MM_ROLE_IDS.items():
        if role_id in user_role_ids:
            user_level = MM_TIERS[tier_key]['level']
            # User can only see tickets at their level or below (except OG sees all)
            if tier_key == 'og':
                return True
            elif user_level >= ticket_level:
                return True
    
    return False

# MM Trade Details Modal
class MMTradeModal(Modal, title='Middleman Trade Details'):
    def __init__(self, tier):
        super().__init__()
        self.tier = tier

        self.trader = TextInput(
            label='Who are you trading with?',
            placeholder='Enter their user or id',
            required=True,
            max_length=100
        )

        self.giving = TextInput(
            label="What are you giving?",
            placeholder='Example: 500 rbx ',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.receiving = TextInput(
            label="What are you receiving?",
            placeholder='Example: $50 PayPal',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.tip = TextInput(
            label='Tip Amount (Optional)',
            placeholder=' Enter the tip if ur willing to tip the middleman',
            required=False,
            max_length=100
        )

        self.add_item(self.trader)
        self.add_item(self.giving)
        self.add_item(self.receiving)
        self.add_item(self.tip)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the channel object returned from create_ticket_with_details
            ticket_channel = await create_ticket_with_details(
                interaction.guild, 
                interaction.user, 
                self.tier,
                self.trader.value,
                self.giving.value,
                self.receiving.value,
                self.tip.value if self.tip.value else 'None'
            )
            
            # Send clickable link to the ticket
            await interaction.followup.send(
                f'✅ Middleman ticket created! {ticket_channel.mention}',
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f'❌ Error creating ticket: {str(e)}', ephemeral=True)

# Support Ticket Modal
class SupportTicketModal(Modal, title='Open Support Ticket'):
    def __init__(self):
        super().__init__()

        self.reason = TextInput(
            label='Reason for Support',
            placeholder='Example: Need help with a trade, Report an issue, etc.',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )

        self.details = TextInput(
            label='Additional Details',
            placeholder='Provide any additional information...',
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
            await interaction.followup.send('✅ Support ticket created! Check the ticket channel.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error creating ticket: {str(e)}', ephemeral=True)

# Support Ticket View (for inside the ticket)
class SupportTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_support_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

# MM Setup View (Persistent)
class MMSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open MM Ticket', emoji='⚖️', style=discord.ButtonStyle.primary, custom_id='open_mm_ticket_main')
    async def open_mm_button(self, interaction: discord.Interaction, button: Button):
        tier_embed = discord.Embed(
            title='Select your middleman tier:',
            color=MM_COLOR
        )
        await interaction.response.send_message(embed=tier_embed, view=TierSelectView(), ephemeral=True)

# Support Setup View (Persistent)
class SupportSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open Support Ticket', emoji='🎫', style=discord.ButtonStyle.primary, custom_id='open_support_ticket_main')
    async def open_support_button(self, interaction: discord.Interaction, button: Button):
        modal = SupportTicketModal()
        await interaction.response.send_modal(modal)

# Tier Selection Dropdown
class TierSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label='$1-$15 Middleman',
                value='basic',
                emoji='💲'
            ),
            discord.SelectOption(
                label='$15-$50 Middleman',
                value='advanced',
                emoji='💸'
            ),
            discord.SelectOption(
                label='$50-$150 Middleman',
                value='premium',
                emoji='💰'
            ),
            discord.SelectOption(
                label='$150+ Middleman',
                value='og',
                emoji='💳'
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

# Coinflip Button View
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
        last_winner = None  # Track last winner
        streak_count = 0    # Track streak length
        
        # FIXED: Different logic for First To vs Best Of
        if self.is_first_to:
            # First to X: Keep going until someone reaches X wins
            while user1_wins < self.total_rounds and user2_wins < self.total_rounds:
                # ANTI-STREAK LOGIC: If 3+ streak, slightly favor the other side
                if streak_count >= 3:
                    # 60% chance to break the streak
                    rand_num = secrets.randbelow(100)
                    if last_winner == 'user1':
                        flip_result = self.user2_choice if rand_num < 60 else self.user1_choice
                    else:
                        flip_result = self.user1_choice if rand_num < 60 else self.user2_choice
                else:
                    # Normal 50/50 flip using secrets module
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
            # Best of X: Play exactly X rounds, winner has most wins
            rounds_to_win = (self.total_rounds // 2) + 1
            
            while rounds_played < self.total_rounds:
                # ANTI-STREAK LOGIC
                if streak_count >= 3:
                    rand_num = secrets.randbelow(100)
                    if last_winner == 'user1':
                        flip_result = self.user2_choice if rand_num < 60 else self.user1_choice
                    else:
                        flip_result = self.user1_choice if rand_num < 60 else self.user2_choice
                else:
                    # Normal 50/50 flip using secrets module
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
                
                # Early finish if someone already won majority
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
        
        # Determine winner
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

# MM Ticket View
class MMTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='✅ Claim Ticket', style=discord.ButtonStyle.success, custom_id='claim_mm_ticket')
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        # Get ticket from DATABASE (not active_tickets dictionary)
        ticket_data = get_ticket(interaction.channel.id)
        if not ticket_data:
            return await interaction.response.send_message('❌ Ticket data not found!', ephemeral=True)
        
        ticket_tier = ticket_data.get('tier') or ticket_data['tier']
        
        if not can_see_tier(interaction.user.roles, ticket_tier) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message('❌ You do not have permission to claim this ticket tier!', ephemeral=True)
        
        # Check if already claimed (from DATABASE)
        if ticket_data.get('claimed_by'):
            claimer = interaction.guild.get_member(ticket_data['claimed_by'])
            return await interaction.response.send_message(f'❌ This ticket is already claimed by {claimer.mention if claimer else "someone"}!', ephemeral=True)
        
        # CLAIM IN DATABASE (not claimed_tickets dictionary)
        claim_ticket_db(interaction.channel.id, interaction.user.id)
        
        ticket_creator_id = ticket_data['user_id']
        ticket_creator = interaction.guild.get_member(ticket_creator_id) if ticket_creator_id else None
        
        await interaction.channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )
        
        if ticket_creator:
            await interaction.channel.set_permissions(
                ticket_creator,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        
        embed = discord.Embed(
            description=f'✅ Ticket claimed by {interaction.user.mention}\n\n🔒 **Only the claimer and ticket creator are allowed to talk.**',
            color=0x57F287
        )
        
        await interaction.response.send_message(embed=embed)
        await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
    
    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_mm_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

# Events
@bot.event
async def on_ready():
    print(f'✅ Bot is online as {bot.user}')
    print(f'📊 Serving {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='Offical Boost Mm Bot'))
    
    bot.add_view(TierSelectView())
    bot.add_view(MMTicketView())
    bot.add_view(SupportTicketView())
    bot.add_view(MMSetupView())
    bot.add_view(SupportSetupView())
    
    init_database()  

# Setup Command
@bot.command(name='mmsetup')
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Create MM ticket panel"""
    embed = discord.Embed(
        title='⚖️ Middleman Services',
        description='Click the button below to open a middleman ticket.\n\n**Available Tiers:**\n💲**$1-$50**\n💸 **$50-$100**\n💰 **$100-$250**\n💳 **$250+** ',
        color=MM_COLOR
    )
    embed.set_footer(text='Select your tier to get started')
    
    view = View(timeout=None)
    button = Button(label='Open MM Ticket', emoji='⚖️', style=discord.ButtonStyle.primary, custom_id='open_mm_ticket')
    
    async def button_callback(interaction: discord.Interaction):
        tier_embed = discord.Embed(
            title='Select your middleman tier:',
            color=MM_COLOR
        )
        await interaction.response.send_message(embed=tier_embed, view=TierSelectView(), ephemeral=True)
    
    button.callback = button_callback
    view.add_item(button)
    
    await ctx.send(embed=embed, view=MMSetupView())
    await ctx.message.delete()

# Support Setup Command
@bot.command(name='supportsetup')
@commands.has_permissions(administrator=True)
async def support_setup(ctx):
    """Create Support ticket panel"""
    embed = discord.Embed(
        title='🎫 Support Center',
        description='Need help? Open a support ticket below!\n\n**What can you use support for?**\n• General Support\n• Claiming a Prize\n• Partnership Inquiries\n• Report an Issue\n• Other Questions',
        color=MM_COLOR
    )
    embed.set_footer(text='Click the button below to open a ticket')
    embed.timestamp = datetime.utcnow()
    
    view = View(timeout=None)
    button = Button(label='Open Support Ticket', emoji='🎫', style=discord.ButtonStyle.primary, custom_id='open_support_ticket')
    
    async def button_callback(interaction: discord.Interaction):
        modal = SupportTicketModal()
        await interaction.response.send_modal(modal)
    
    button.callback = button_callback
    view.add_item(button)
    
    await ctx.send(embed=embed, view=SupportSetupView())
    await ctx.message.delete()

@bot.command(name='claim')
async def claim(ctx):
    """Claim a ticket"""
    
    if not is_mm_or_admin(ctx.author, ctx.guild):
        return await ctx.reply('❌ You do not have permission to use this command!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    # ✅ Get ticket from DATABASE
    ticket_data = get_ticket(ctx.channel.id)
    if not ticket_data:
        return await ctx.reply('❌ Ticket data not found!')
    
    # ✅ Check if already claimed (from DATABASE)
    if ticket_data.get('claimed_by'):
        claimer = ctx.guild.get_member(ticket_data['claimed_by'])
        return await ctx.reply(f'❌ This ticket is already claimed by {claimer.mention if claimer else "someone"}!')
    
    ticket_tier = ticket_data.get('tier')
    
    # Check permissions for MM tickets
    if ticket_tier and not can_see_tier(ctx.author.roles, ticket_tier) and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ You do not have permission to claim this ticket tier!')

    # ✅ Claim in DATABASE
    claim_ticket_db(ctx.channel.id, ctx.author.id)
    
    ticket_creator_id = ticket_data['user_id']
    ticket_creator = ctx.guild.get_member(ticket_creator_id) if ticket_creator_id else None
    
    await ctx.channel.set_permissions(
        ctx.author,
        view_channel=True,
        send_messages=True,
        read_message_history=True
    )
    
    if ticket_creator:
        await ctx.channel.set_permissions(
            ticket_creator,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )
    
    embed = discord.Embed(
        description=f'✅ Ticket claimed by {ctx.author.mention}\n\n🔒 **Only the claimer and ticket creator can now send messages.**',
        color=0x57F287
    )
    embed.timestamp = datetime.utcnow()

    await ctx.send(embed=embed)
    await ctx.channel.edit(name=f"{ctx.channel.name}-claimed")

# unclaim
@bot.command(name='unclaim')
async def unclaim_command(ctx):
    """Unclaim a ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')
    
    # GET FROM DATABASE (not claimed_tickets dictionary)
    ticket_data = get_ticket(ctx.channel.id)
    if not ticket_data:
        return await ctx.reply('❌ Ticket data not found!')
    
    if not ticket_data.get('claimed_by'):
        return await ctx.reply('❌ This ticket is not claimed!')
    
    claimer_id = ticket_data['claimed_by']
    
    if ctx.author.id != claimer_id and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ Only the ticket claimer or administrators can unclaim this ticket!')
    
    ticket_tier = ticket_data.get('tier')
    ticket_creator_id = ticket_data['user_id']
    ticket_creator = ctx.guild.get_member(ticket_creator_id) if ticket_creator_id else None
    
    # UNCLAIM IN DATABASE (not claimed_tickets dictionary)
    unclaim_ticket_db(ctx.channel.id)
    
    # Restore permissions
    if ticket_tier:
        ticket_level = MM_TIERS[ticket_tier]['level']
        
        for tier_key, role_id in MM_ROLE_IDS.items():
            role = ctx.guild.get_role(role_id)
            if role:
                tier_lvl = MM_TIERS[tier_key]['level']
                if tier_key == 'og' or tier_lvl >= ticket_level:
                    await ctx.channel.set_permissions(
                        role,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True
                    )
    
    new_name = ctx.channel.name.replace('-claimed', '')
    await ctx.channel.edit(name=new_name)
    
    embed = discord.Embed(
        description=f'✅ Ticket unclaimed by {ctx.author.mention}\n\n🔓 **All eligible middlemen can now claim this ticket again.**',
        color=MM_COLOR
    )
    
    await ctx.reply(embed=embed)

# Close Command
@bot.command(name='close')
async def close_command(ctx):
    """Close a ticket"""
    
    if not is_mm_or_admin(ctx.author, ctx.guild):
        return await ctx.reply('❌ You do not have permission to use this command!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    embed = discord.Embed(
        title='⚠️ Close Ticket',
        description='Are you sure you want to close this ticket?',
        color=0xED4245
    )
    embed.set_footer(text='This action cannot be undone')

    view = View(timeout=60)
    
    confirm_button = Button(label='Confirm', style=discord.ButtonStyle.danger)
    cancel_button = Button(label='Cancel', style=discord.ButtonStyle.secondary)
    
    async def confirm_callback(interaction):
        await interaction.response.defer()
        await close_ticket(ctx.channel, ctx.author)
    
    async def cancel_callback(interaction):
        await interaction.response.edit_message(content='❌ Ticket closure cancelled.', embed=None, view=None)
    
    confirm_button.callback = confirm_callback
    cancel_button.callback = cancel_callback
    
    view.add_item(confirm_button)
    view.add_item(cancel_button)

    await ctx.reply(embed=embed, view=view)

# Add/Remove User Commands
@bot.command(name='add')
async def add_user(ctx, member: discord.Member = None):
    """Add user to ticket"""

# Permission check
    if not is_mm_or_admin(ctx.author, ctx.guild):
        return await ctx.reply('❌ You do not have permission to use this command!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been added to the ticket',
        color=0x57F287
    )

    await ctx.reply(embed=embed)

@bot.command(name='remove')
async def remove_user(ctx, member: discord.Member = None):
    """Remove user from ticket"""

    # Permission check
    if not is_mm_or_admin(ctx.author, ctx.guild):
        return await ctx.reply('❌ You do not have permission to use this command!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been removed from the ticket',
        color=0x57F287
    )

    await ctx.reply(embed=embed)

# Proof Command
@bot.command(name='proof')
async def proof_command(ctx):
    """Send MM proof to proof channel"""
    
    if not is_mm_or_admin(ctx.author, ctx.guild):
        return await ctx.reply('❌ You do not have permission to use this command!')
    
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in a ticket.')

    # GET FROM DATABASE (not active_tickets dictionary)
    ticket = get_ticket(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ No ticket data found.')

    requester = ctx.guild.get_member(ticket['user_id'])
    trader = ticket.get('trader', 'Unknown')
    giving = ticket.get('giving', 'Unknown')
    receiving = ticket.get('receiving', 'Unknown')
    tier = ticket.get('tier', 'Unknown')

    proof_channel = ctx.guild.get_channel(PROOF_CHANNEL_ID)

    if not proof_channel:
        return await ctx.reply('❌ Proof channel not found.')

    embed = discord.Embed(
        title='✅ Trade Completed',
        color=0x57F287
    )

    embed.add_field(name='Middleman', value=ctx.author.mention, inline=False)
    if tier and tier in MM_TIERS:
        embed.add_field(name='Tier', value=MM_TIERS[tier]['name'], inline=False)
    embed.add_field(name='Requester', value=requester.mention if requester else 'Unknown', inline=False)
    embed.add_field(name='Trader', value=trader, inline=False)
    embed.add_field(name='Gave', value=giving, inline=False)
    embed.add_field(name='Received', value=receiving, inline=False)

    ticket_number = ctx.channel.name.replace('ticket-', '') 
    embed.set_footer(text=f"Ticket #{ticket_number}")
    embed.timestamp = datetime.utcnow()

    await proof_channel.send(embed=embed)
    
    # INCREMENT STATS IN DATABASE (not mm_stats dictionary)
    increment_mm_stats(ctx.author.id)
    
    await ctx.reply('✅ Proof sent successfully!')

# Help Command
@bot.command(name='help')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title='📋 Bot Commands',
        description='Here are all available commands:',
        color=MM_COLOR
    )
    
    embed.add_field(
        name='🎫 Ticket Commands',
        value='`$mmsetup` - Create MM ticket panel (Admin only)\n'
              '`$supportsetup` - Create Support ticket panel (Admin only)\n'
              '`$claim` - Claim a ticket\n'
              '`$unclaim` - Unclaim a ticket\n'
              '`$close` - Close a ticket\n'
              '`$add @user` - Add user to ticket\n'
              '`$remove @user` - Remove user from ticket\n'
              '`$proof` - Send proof to proof channel',
        inline=False
    )
    
    embed.add_field(
        name='📊 Statistics Commands',
        value='`$mmstats [@user]` - View MM statistics\n'
              '`$mmleaderboard` - View top middlemen',
        inline=False
    )
    
    embed.add_field(
        name='🪙 Coinflip Commands',
        value='`$cf @user1 vs @user2 ft <number>` - First to X wins\n'
              '`$coinflip` - Flip a single coin (heads or tails)\n'
              '`$cf @user1 vs @user2 bo <number>` - Best of X rounds\n\n'
              '**Examples:**\n'
              '• `$cf @user1 vs @user2 ft 10` (First to reach 10 wins)\n'
              '• `$cf @user1 vs @user2 bo 10` (Best of 10 rounds, need 6 to win)',
        inline=False
    )
    
    embed.set_footer(text='Use $help to see this message again')
    
    await ctx.reply(embed=embed)

# mm stats cmd
@bot.command(name='mmstats')
async def mmstats_command(ctx, member: discord.Member = None):
    """View MM statistics for a user"""
    target = member if member else ctx.author
    
    # GET FROM DATABASE (not mm_stats dictionary)
    stats = get_mm_stats_db(target.id)
    
    tickets_completed = stats.get('tickets_completed', 0)
    
    embed = discord.Embed(
        title=f'📊 Middleman Statistics',
        description=f'Statistics for {target.mention}',
        color=MM_COLOR
    )
    
    embed.add_field(
        name='✅ Tickets Completed',
        value=f'**{tickets_completed}** tickets',
        inline=False
    )
    
    # Calculate rank from database
    all_stats = get_mm_leaderboard_db(1000)  # Get all to calculate rank
    rank = next((i + 1 for i, s in enumerate(all_stats) if s['user_id'] == target.id), None)
    
    if rank:
        embed.add_field(
            name='🏆 Rank',
            value=f'#{rank} out of {len(all_stats)} middlemen',
            inline=False
        )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    
    await ctx.reply(embed=embed)

# mm lb cmd
@bot.command(name='mmleaderboard')
async def mmleaderboard_command(ctx):
    """View top middlemen leaderboard"""
    
    # GET FROM DATABASE (not mm_stats dictionary)
    sorted_stats = get_mm_leaderboard_db(10)
    
    if not sorted_stats:
        return await ctx.reply('❌ No middleman statistics available yet!')
    
    embed = discord.Embed(
        title='🏆 Middleman Leaderboard',
        description='Top middlemen by completed tickets',
        color=MM_COLOR
    )
    
    leaderboard_text = []
    for i, entry in enumerate(sorted_stats, 1):
        member = ctx.guild.get_member(entry['user_id'])
        if member:
            medal = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            leaderboard_text.append(f'{medal} {member.mention} - **{entry["tickets_completed"]}** tickets')
    
    if leaderboard_text:
        embed.description = '\n'.join(leaderboard_text)
    else:
        embed.description = 'No data available'
    
    all_stats = get_mm_leaderboard_db(1000)
    embed.set_footer(text=f'Total Middlemen: {len(all_stats)}')
    
    await ctx.reply(embed=embed)

# Simple Coinflip Command
@bot.command(name='coinflip')
async def simple_coinflip(ctx):
    """Flip a single coin"""
    
    # Flipping animation
    embed = discord.Embed(
        title=' Flipping Coin...',
        description='The coin is in the air!',
        color=MM_COLOR
    )
    
    msg = await ctx.reply(embed=embed)
    await asyncio.sleep(1.5)
    
    # Get result
    result = 'Heads' if secrets.randbelow(2) == 0 else 'Tails'
    
    # Result embed
    result_embed = discord.Embed(
        title=f'{result}!',
        description=f'The coin landed on **{result}**!',
        color=0x57F287 if result == 'Heads' else 0x5865F2
    )
    result_embed.set_footer(text=f'Flipped by {ctx.author.name}', icon_url=ctx.author.display_avatar.url)
    
    await msg.edit(embed=result_embed)

# Coinflip Command
@bot.command(name='cf')
async def coinflip(ctx, user1_input: str = None, vs: str = None, user2_input: str = None, mode: str = None, rounds: int = None):
    """
    Coinflip command
    Usage: $cf @user1 vs @user2 ft 3
           $cf user1 vs user2 5
    """
    # Validate inputs
    if not all([user1_input, vs, user2_input]):
        return await ctx.reply('❌ Usage: `$cf @user1 vs @user2 [ft] <number>`\nExample: `$cf @user1 vs @user2 ft 3` or `$cf user1 vs user2 5`')
    
    if vs.lower() != 'vs':
        return await ctx.reply('❌ Please use "vs" between usernames!\nExample: `$cf @user1 vs @user2 ft 3`')
    
    # Convert user inputs to Member objects
    user1 = None
    user2 = None
    
    # Try to find user1
    if user1_input.startswith('<@'):
        try:
            user_id = int(user1_input.strip('<@!>'))
            user1 = ctx.guild.get_member(user_id)
        except:
            pass
    else:
        user1 = discord.utils.find(lambda m: m.name.lower() == user1_input.lower() or (m.nick and m.nick.lower() == user1_input.lower()), ctx.guild.members)
    
    # Try to find user2
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
    
    # Parse mode and rounds
    is_first_to = False
    total_rounds = 1
    
    if mode:
        if mode.lower() == 'ft':
            if rounds is None:
                return await ctx.reply('❌ Please specify the number of rounds for "ft" mode!\nExample: `$cf @user1 vs @user2 ft 3`')
            is_first_to = True
            total_rounds = rounds
        elif mode.isdigit():
            total_rounds = int(mode)
            is_first_to = False
        else:
            return await ctx.reply('❌ Invalid mode! Use "ft" for first to, or just a number for best of.')
    
    if total_rounds < 1 or total_rounds > 200:
        return await ctx.reply('❌ Number of rounds must be between 1 and 200!')
    
    # Create initial embed
    mode_text = f"First to {total_rounds}" if is_first_to else f"Best of {total_rounds}"
    
    embed = discord.Embed(
        title='🪙 Choose Your Side',
        description=f'**{user1.mention}** vs **{user2.mention}**\n\n**Mode:** {mode_text}\n\n**Select your side below:**',
        color=MM_COLOR
    )
    
    
    view = CoinflipView(user1, user2, total_rounds, is_first_to)
    await ctx.send(embed=embed, view=view)

# Helper Functions
async def create_ticket_with_details(guild, user, tier, trader, giving, receiving, tip):
    """Create MM ticket with tier-based permissions"""
    try:
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY, position=len(guild.categories))
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=True, 
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }
        
        ticket_level = MM_TIERS[tier]['level']
        
        # Collect roles to ping
        roles_to_ping = []
        
        for tier_key, role_id in MM_ROLE_IDS.items():
            role = guild.get_role(role_id)
            if role:
                tier_lvl = MM_TIERS[tier_key]['level']
                if tier_key == 'og' or tier_lvl >= ticket_level:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True
                    )
                    roles_to_ping.append(role)
        
        ticket_channel = await guild.create_text_channel(
            name=f'ticket-{user.name}-mm',
            category=category,
            overwrites=overwrites
        )
        
        # SAVE TO DATABASE (instead of active_tickets dictionary)
        save_ticket(
            ticket_channel.id,
            user.id,
            'mm',
            tier=tier,
            trader=trader,
            giving=giving,
            receiving=receiving,
            tip=tip
        )
        
        # PING ROLES + USER (NO GHOST PING - just normal ping)
        if roles_to_ping:
            ping_mentions = ' '.join([role.mention for role in roles_to_ping]) + f' {user.mention}'
            await ticket_channel.send(ping_mentions)
        else:
            await ticket_channel.send(user.mention)
        
        # Send ticket embed
        embed = discord.Embed(
            title=f"{MM_TIERS[tier]['emoji']} {MM_TIERS[tier]['name']}",
            description=f"Welcome {user.mention}!\n\nOur team will be with you shortly.",
            color=MM_COLOR
        )
        
        embed.add_field(name="💥 Trading With", value=trader, inline=False)
        embed.add_field(name="📤 You're Giving", value=giving, inline=True)
        embed.add_field(name="📥 You're Receiving", value=receiving, inline=True)
        embed.add_field(name="💰 Tip", value=tip if tip else "None", inline=True)
        
        await ticket_channel.send(embed=embed, view=MMTicketView())
        
        # RETURN THE CHANNEL (so we can send link to user)
        return ticket_channel
        
    except Exception as e:
        print(f'[ERROR] MM Ticket creation failed: {e}')
        raise
        
async def create_support_ticket(guild, user, reason, details):
    """Create a support ticket with staff ping"""
    try:
        category = discord.utils.get(guild.categories, name=SUPPORT_CATEGORY)
        if not category:
            category = await guild.create_category(SUPPORT_CATEGORY)
        
        # Get staff role
        staff_role = guild.get_role(STAFF_ROLE_ID)
        
        # Base overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=True, 
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }
        
        # Add staff role permissions
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )
        
        # Create ticket channel
        ticket_channel = await guild.create_text_channel(
            name=f'ticket-{user.name}-support',
            category=category,
            overwrites=overwrites
        )
        
        # ✅ SAVE TO DATABASE (instead of active_tickets dictionary)
        save_ticket(
            ticket_channel.id,
            user.id,
            'support',
            reason=reason,
            details=details
        )
        
        # Ping user and staff
        if staff_role:
            await ticket_channel.send(f"{staff_role.mention} {user.mention}")
        else:
            await ticket_channel.send(user.mention)
        
        # Send ticket embed
        embed = discord.Embed(
            title='🎫 Support Ticket',
            description=f"Welcome {user.mention}!\n\nOur staff team will be with you shortly.",
            color=MM_COLOR
        )
        
        embed.add_field(
            name="📋 Reason",
            value=reason,
            inline=False
        )
        
        embed.add_field(
            name="📝 Details",
            value=details,
            inline=False
        )
        
        embed.set_footer(
            text=f'Ticket created by {user.name}',
            icon_url=user.display_avatar.url
        )
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
        color=0xED4245
    )
    embed.timestamp = datetime.utcnow()

    await channel.send(embed=embed)

    # DELETE FROM DATABASE (not dictionaries)
    delete_ticket_db(channel.id)

    await asyncio.sleep(5)
    await channel.delete()
        
# Run Bot
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.getenv('TOKEN')
    if not TOKEN:
        print('❌ ERROR: No TOKEN found in environment variables!')
    else:
        print('🚀 Starting MM Bot...')
        bot.run(TOKEN)
