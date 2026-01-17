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

# Flask
app = Flask('')

@app.route('/')
def home():
    return "<h1>Bot Active ✅</h1>"

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Config
PREFIX = os.getenv('PREFIX', '$')
DATABASE_URL = os.getenv('DATABASE_URL')
TOKEN = os.getenv('TOKEN')

MM_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245

MM_TIERS = {
    '1_50': {'name': '$1-$50 Middleman', 'range': '$1-$50', 'emoji': '🟢', 'level': 1},
    '50_100': {'name': '$50-$100 Middleman', 'range': '$50-$100', 'emoji': '🔵', 'level': 2},
    '100_250': {'name': '$100-$250 Middleman', 'range': '$100-$250', 'emoji': '🟣', 'level': 3},
    '250_plus': {'name': '$250+ Middleman', 'range': '$250+', 'emoji': '💎', 'level': 4}
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ============ AUTO-CREATE TABLES ============

def init_database():
    """Creates all tables automatically on startup"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key VARCHAR(255) PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
                status VARCHAR(50) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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

# ============ DATABASE FUNCTIONS ============

def get_db():
    return psycopg2.connect(DATABASE_URL)

def get_config(key):
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
    roles = {}
    for tier in ['1_50', '50_100', '100_250', '250_plus']:
        value = get_config(f'mm_role_{tier}')
        if value and value != '0':
            roles[tier] = int(value)
    return roles

def create_ticket_db(channel_id, user_id, ticket_type, **kwargs):
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

def get_ticket_db(channel_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tickets WHERE channel_id = %s", (channel_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result

def claim_ticket_db(channel_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = %s, status = 'claimed' WHERE channel_id = %s", (user_id, channel_id))
    conn.commit()
    cur.close()
    conn.close()

def unclaim_ticket_db(channel_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET claimed_by = NULL, status = 'open' WHERE channel_id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()

def delete_ticket_db(channel_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE channel_id = %s", (channel_id,))
    conn.commit()
    cur.close()
    conn.close()

def increment_mm_stats(user_id):
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
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM mm_stats WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result if result else {'user_id': user_id, 'tickets_completed': 0}

def get_mm_leaderboard(limit=10):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id, tickets_completed FROM mm_stats ORDER BY tickets_completed DESC LIMIT %s", (limit,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def get_mm_rank(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) + 1 as rank FROM mm_stats
        WHERE tickets_completed > (SELECT COALESCE(tickets_completed, 0) FROM mm_stats WHERE user_id = %s)
    """, (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result['rank'] if result else None

def can_access_tier(user_roles, ticket_tier):
    """Check if user can access this tier - higher tiers can see lower, but not vice versa"""
    mm_role_ids = get_all_mm_roles()
    user_role_ids = [role.id for role in user_roles]
    ticket_level = MM_TIERS[ticket_tier]['level']
    
    for tier_key, role_id in mm_role_ids.items():
        if role_id in user_role_ids:
            user_level = MM_TIERS[tier_key]['level']
            # User can see this ticket if their level >= ticket level
            if user_level >= ticket_level:
                return True
    return False

def is_mm_or_staff(user):
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

# ============ MODALS ============

class MMTradeModal(Modal, title='Middleman Trade Details'):
    def __init__(self, tier):
        super().__init__()
        self.tier = tier
        
        self.trader = TextInput(label='Who are you trading with?', placeholder='@username or Discord ID', required=True, max_length=100)
        self.giving = TextInput(label='What are you giving?', placeholder='Example: 100 Robux', style=discord.TextStyle.paragraph, required=True, max_length=500)
        self.receiving = TextInput(label='What are they giving?', placeholder='Example: $50 PayPal', style=discord.TextStyle.paragraph, required=True, max_length=500)
        self.tip = TextInput(label='Will you tip the middleman?', placeholder='Optional', required=False, max_length=200)
        
        self.add_item(self.trader)
        self.add_item(self.giving)
        self.add_item(self.receiving)
        self.add_item(self.tip)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await create_mm_ticket(interaction.guild, interaction.user, self.tier, self.trader.value, self.giving.value, self.receiving.value, self.tip.value if self.tip.value else 'None')
            await interaction.followup.send('✅ Ticket created!', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error: {str(e)}', ephemeral=True)

class SupportTicketModal(Modal, title='Open Support Ticket'):
    def __init__(self):
        super().__init__()
        self.reason = TextInput(label='Reason for Support', placeholder='Example: Need help', style=discord.TextStyle.paragraph, required=True, max_length=1000)
        self.details = TextInput(label='Additional Details', placeholder='Optional', style=discord.TextStyle.paragraph, required=False, max_length=2000)
        self.add_item(self.reason)
        self.add_item(self.details)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await create_support_ticket(interaction.guild, interaction.user, self.reason.value, self.details.value if self.details.value else 'None')
            await interaction.followup.send('✅ Support ticket created!', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error: {str(e)}', ephemeral=True)

# ============ VIEWS ============

class MMSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open MM Ticket', emoji='⚖️', style=discord.ButtonStyle.primary, custom_id='open_mm_ticket_main')
    async def open_mm_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title='🎯 Select Your Tier', description='Choose based on your trade value:', color=MM_COLOR)
        await interaction.response.send_message(embed=embed, view=TierSelectView(), ephemeral=True)

class SupportSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Open Support Ticket', emoji='🎫', style=discord.ButtonStyle.primary, custom_id='open_support_ticket_main')
    async def open_support_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SupportTicketModal())

class TierSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label='$1-$50 Middleman', value='1_50', emoji='🟢'),
            discord.SelectOption(label='$50-$100 Middleman', value='50_100', emoji='🔵'),
            discord.SelectOption(label='$100-$250 Middleman', value='100_250', emoji='🟣'),
            discord.SelectOption(label='$250+ Middleman', value='250_plus', emoji='💎')
        ]
        super().__init__(placeholder='Select tier', options=options, custom_id='tier_select')
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MMTradeModal(self.values[0]))

class TierSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TierSelect())

class MMTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='✅ Claim', style=discord.ButtonStyle.success, custom_id='claim_mm_ticket')
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        ticket = get_ticket_db(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message('❌ Ticket not found!', ephemeral=True)
        
        if not can_access_tier(interaction.user.roles, ticket['tier']) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message('❌ No permission!', ephemeral=True)
        
        if ticket['claimed_by']:
            return await interaction.response.send_message('❌ Already claimed!', ephemeral=True)
        
        claim_ticket_db(interaction.channel.id, interaction.user.id)
        
        ticket_creator = interaction.guild.get_member(ticket['user_id'])
        await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
        if ticket_creator:
            await interaction.channel.set_permissions(ticket_creator, view_channel=True, send_messages=True)
        
        embed = discord.Embed(description=f'✅ Claimed by {interaction.user.mention}', color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=embed)
        await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
    
    @discord.ui.button(label='🔒 Close', style=discord.ButtonStyle.danger, custom_id='close_mm_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

class SupportTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='🔒 Close', style=discord.ButtonStyle.danger, custom_id='close_support_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

# ============ BOT EVENTS ============

@bot.event
async def on_ready():
    print(f'✅ {bot.user} online')
    init_database()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='Middleman Services'))
    
    bot.add_view(TierSelectView())
    bot.add_view(MMTicketView())
    bot.add_view(SupportTicketView())
    bot.add_view(MMSetupView())
    bot.add_view(SupportSetupView())

# ============ COMMANDS ============

@bot.command(name='mmsetup')
@commands.has_permissions(administrator=True)
async def mmsetup(ctx):
    embed = discord.Embed(color=MM_COLOR)
    embed.set_author(name='⚖️ Middleman Services', icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    embed.description = (
        '**Safe & Secure Trading**\n'
        'We protect both parties during the transaction\n\n'
        '🟢 • **$1 - $50** • \n'
        '🔵 • **$50 - $100** • \n'
        '🟣 • **$100 - $250** • \n'
        '💎 • **$250+** • \n\n'
        '✅ Verified Middlemen\n'
        '🔒 100% Secure'
    )
    await ctx.send(embed=embed, view=MMSetupView())
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='supportsetup')
@commands.has_permissions(administrator=True)
async def supportsetup(ctx):
    embed = discord.Embed(color=MM_COLOR)
    embed.set_author(name='🎫 Support Center', icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    embed.description = (
        '**Need Assistance?**\n'
        'Our staff team is ready to help you\n\n'
        '📌 General Questions\n'
        '⚠️ Report Issues\n'
        '🎉 Claim a prize\n'
        '🤝 Partnership\n'
        '💬 Get Help\n\n'
        '**Average Response:** Under 5 minutes'
    )
    await ctx.send(embed=embed, view=SupportSetupView())
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='setrole')
@commands.has_permissions(administrator=True)
async def setrole(ctx, tier: str, role: discord.Role):
    valid = ['1_50', '50_100', '100_250', '250_plus', 'staff', 'mm_team']
    if tier not in valid:
        return await ctx.reply(f'❌ Use: {", ".join(valid)}')
    set_config(f'mm_role_{tier}' if tier not in ['staff', 'mm_team'] else tier + '_role', role.id)
    await ctx.reply(f'✅ Set {tier} to {role.mention}')

@bot.command(name='setproof')
@commands.has_permissions(administrator=True)
async def setproof(ctx, channel: discord.TextChannel):
    set_config('proof_channel', channel.id)
    await ctx.reply(f'✅ Proof channel: {channel.mention}')

@bot.command(name='claim')
async def claim(ctx):
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ No permission!')
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ Not a ticket!')
    
    ticket = get_ticket_db(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ Not found!')
    if ticket['claimed_by']:
        return await ctx.reply('❌ Already claimed!')
    
    claim_ticket_db(ctx.channel.id, ctx.author.id)
    await ctx.send(f'✅ Claimed by {ctx.author.mention}')
    await ctx.channel.edit(name=f"{ctx.channel.name}-claimed")

@bot.command(name='unclaim')
async def unclaim(ctx):
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ Not a ticket!')
    
    ticket = get_ticket_db(ctx.channel.id)
    if not ticket or not ticket['claimed_by']:
        return await ctx.reply('❌ Not claimed!')
    
    unclaim_ticket_db(ctx.channel.id)
    await ctx.reply('✅ Unclaimed')
    await ctx.channel.edit(name=ctx.channel.name.replace('-claimed', ''))

@bot.command(name='close')
async def close_cmd(ctx):
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ No permission!')
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ Not a ticket!')
    
    await ctx.send('🔒 Closing in 5 seconds...')
    await close_ticket(ctx.channel, ctx.author)

@bot.command(name='add')
async def add_user(ctx, member: discord.Member):
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ No permission!')
    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)
    await ctx.reply(f'✅ Added {member.mention}')

@bot.command(name='remove')
async def remove_user(ctx, member: discord.Member):
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ No permission!')
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.reply(f'✅ Removed {member.mention}')

@bot.command(name='proof')
async def proof_cmd(ctx):
    if not is_mm_or_staff(ctx.author):
        return await ctx.reply('❌ No permission!')
    
    ticket = get_ticket_db(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ No ticket data!')
    
    proof_channel_id = get_config('proof_channel')
    if not proof_channel_id:
        return await ctx.reply('❌ Set proof channel with $setproof')
    
    proof_channel = ctx.guild.get_channel(int(proof_channel_id))
    if not proof_channel:
        return await ctx.reply('❌ Channel not found!')
    
    requester = ctx.guild.get_member(ticket['user_id'])
    embed = discord.Embed(title='✅ Trade Completed', color=SUCCESS_COLOR)
    embed.add_field(name='MM', value=ctx.author.mention, inline=False)
    embed.add_field(name='Tier', value=MM_TIERS[ticket['tier']]['name'], inline=False)
    embed.add_field(name='Requester', value=requester.mention if requester else 'Unknown', inline=False)
    embed.add_field(name='Trader', value=ticket.get('trader', 'Unknown'), inline=False)
    embed.add_field(name='Gave', value=ticket.get('giving', 'Unknown'), inline=True)
    embed.add_field(name='Received', value=ticket.get('receiving', 'Unknown'), inline=True)
    
    await proof_channel.send(embed=embed)
    increment_mm_stats(ctx.author.id)
    await ctx.reply('✅ Proof sent!')

@bot.command(name='mmstats')
async def mmstats_cmd(ctx, member: discord.Member = None):
    target = member if member else ctx.author
    stats = get_mm_stats(target.id)
    rank = get_mm_rank(target.id)
    
    embed = discord.Embed(title='📊 MM Stats', description=f'{target.mention}', color=MM_COLOR)
    embed.add_field(name='✅ Completed', value=f'{stats["tickets_completed"]} tickets', inline=False)
    if rank:
        embed.add_field(name='🏆 Rank', value=f'#{rank}', inline=False)
    
    await ctx.reply(embed=embed)

@bot.command(name='mmleaderboard')
async def mmleaderboard_cmd(ctx):
    lb = get_mm_leaderboard(10)
    if not lb:
        return await ctx.reply('❌ No data!')
    
    embed = discord.Embed(title='🏆 MM Leaderboard', color=MM_COLOR)
    text = []
    for i, entry in enumerate(lb, 1):
        member = ctx.guild.get_member(entry['user_id'])
        if member:
            medal = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            text.append(f'{medal} {member.mention} - {entry["tickets_completed"]} tickets')
    
    embed.description = '\n'.join(text)
    await ctx.reply(embed=embed)

@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(title='📋 Bot Commands', color=MM_COLOR)
    
    # Setup Commands
    setup_cmds = (
        "**`$mmsetup`** - Creates the middleman ticket panel\n"
        "**`$supportsetup`** - Creates the support ticket panel\n"
        "**`$setrole <tier> <role>`** - Set MM/Staff roles\n"
        "  • Tiers: `1_50`, `50_100`, `100_250`, `250_plus`, `staff`, `mm_team`\n"
        "**`$setproof <channel>`** - Set the channel for completed trade proofs"
    )
    embed.add_field(name='⚙️ Setup (Admin Only)', value=setup_cmds, inline=False)
    
    # Ticket Management
    ticket_cmds = (
        "**`$claim`** - Claim a ticket to assist the user\n"
        "**`$unclaim`** - Unclaim a ticket you previously claimed\n"
        "**`$close`** - Close and delete the current ticket\n"
        "**`$add <member>`** - Add a user to the ticket\n"
        "**`$remove <member>`** - Remove a user from the ticket\n"
        "**`$proof`** - Send proof of completed trade to proof channel"
    )
    embed.add_field(name='🎫 Ticket Management', value=ticket_cmds, inline=False)
    
    # Stats Commands
    stats_cmds = (
        "**`$mmstats [member]`** - View MM statistics for yourself or another member\n"
        "**`$mmleaderboard`** - View top 10 middlemen by completed tickets"
    )
    embed.add_field(name='📊 Statistics', value=stats_cmds, inline=False)
    
    embed.set_footer(text='Use $help to see this menu anytime')
    await ctx.reply(embed=embed)

# ============ HELPER FUNCTIONS ============

async def create_mm_ticket(guild, user, tier, trader, giving, receiving, tip):
    # Find or create category at the BOTTOM of the server
    category = discord.utils.get(guild.categories, name='MM Tickets')
    if not category:
        # Create category at the bottom by setting position to max
        category = await guild.create_category('MM Tickets', position=len(guild.categories))
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }
    
    mm_role_ids = get_all_mm_roles()
    ticket_level = MM_TIERS[tier]['level']
    
    # Collect roles to ping
    roles_to_ping = []
    
    # Only add MM roles that have high enough level to see this ticket
    for tier_key, role_id in mm_role_ids.items():
        role = guild.get_role(role_id)
        if role:
            role_level = MM_TIERS[tier_key]['level']
            # Role can see ticket if role_level >= ticket_level
            if role_level >= ticket_level:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
                roles_to_ping.append(role)
    
    channel = await guild.create_text_channel(f'ticket-{user.name}-mm', category=category, overwrites=overwrites)
    
    create_ticket_db(channel.id, user.id, 'mm', tier=tier, trader=trader, giving=giving, receiving=receiving, tip=tip)
    
    # Ping all eligible MM roles + ticket creator
    if roles_to_ping:
        ping_mentions = ' '.join([role.mention for role in roles_to_ping]) + f' {user.mention}'
        await channel.send(ping_mentions)
    else:
        await channel.send(user.mention)
    
    embed = discord.Embed(title=f"{MM_TIERS[tier]['emoji']} {MM_TIERS[tier]['name']}", description=f"Welcome {user.mention}!", color=MM_COLOR)
    embed.add_field(name="Trading With", value=trader, inline=False)
    embed.add_field(name="You're Giving", value=giving, inline=True)
    embed.add_field(name="You're Receiving", value=receiving, inline=True)
    embed.add_field(name="Tip", value=tip, inline=True)
    
    await channel.send(embed=embed, view=MMTicketView())

async def create_support_ticket(guild, user, reason, details):
    # Find or create category at the BOTTOM of the server
    category = discord.utils.get(guild.categories, name='Support Tickets')
    if not category:
        # Create category at the bottom by setting position to max
        category = await guild.create_category('Support Tickets', position=len(guild.categories))
    
    staff_role_id = get_config('staff_role')
    staff_role = guild.get_role(int(staff_role_id)) if staff_role_id and staff_role_id != '0' else None
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }
    
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
    
    channel = await guild.create_text_channel(f'ticket-{user.name}-support', category=category, overwrites=overwrites)
    
    create_ticket_db(channel.id, user.id, 'support', reason=reason, details=details)
    
    # Ping staff role + ticket creator if staff role is set
    if staff_role:
        await channel.send(f'{staff_role.mention} {user.mention}')
    else:
        await channel.send(user.mention)
    
    embed = discord.Embed(title='🎫 Support Ticket', description=f"Welcome {user.mention}!", color=MM_COLOR)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Details", value=details, inline=False)
    
    await channel.send(embed=embed, view=SupportTicketView())

async def close_ticket(channel, user):
    embed = discord.Embed(title='🔒 Ticket Closed', description=f'Closed by {user.mention}', color=ERROR_COLOR)
    await channel.send(embed=embed)
    delete_ticket_db(channel.id)
    await asyncio.sleep(5)
    await channel.delete()

# ============ RUN BOT ============

if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print('❌ No TOKEN!')
    else:
        print('🚀 Starting...')
        bot.run(TOKEN)
