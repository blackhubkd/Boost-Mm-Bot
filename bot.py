import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
import os
import json
from datetime import datetime
import asyncio
from flask import Flask
from threading import Thread

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
TICKET_CATEGORY = 'MM Tickets'

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Storage
active_tickets = {}
claimed_tickets = {}

# Color
MM_COLOR = 0xFEE75C

# MM Tier definitions - UPDATED
MM_TIERS = {
    'basic': {'name': '0-150M Middleman', 'range': '0-150M'},
    'advanced': {'name': '150-500M Middleman', 'range': '150M-500M'},
    'premium': {'name': '500M+ Middleman', 'range': '500M+'},
    'og': {'name': 'OG Middleman', 'range': 'All Trades'}
}

# MM Role IDs - UPDATE THESE WITH YOUR ROLE IDS
MM_ROLE_IDS = {
    "basic": 1458128965351768064,        # 0-150M role ID
    "advanced": 1458129219862134794,     # 150-500M role ID
    "premium": 1458129300065751141,      # 500M+ role ID
    "og": 1458129476423778305            # OG MM role ID
}

def save_data():
    data = {
        'active_tickets': active_tickets,
        'claimed_tickets': claimed_tickets
    }
    with open('bot_data.json', 'w') as f:
        json.dump(data, f, indent=4)

def load_data():
    global active_tickets, claimed_tickets
    try:
        with open('bot_data.json', 'r') as f:
            data = json.load(f)
            active_tickets.update(data.get('active_tickets', {}))
            claimed_tickets.update(data.get('claimed_tickets', {}))
        print('✅ Data loaded successfully!')
    except FileNotFoundError:
        print('⚠️ No saved data found, starting fresh.')
    except Exception as e:
        print(f'❌ Error loading data: {e}')

# MM Trade Details Modal
class MMTradeModal(Modal, title='Middleman Trade Details'):
    def __init__(self, tier):
        super().__init__()
        self.tier = tier

        self.trader = TextInput(
            label='Who are you trading with?',
            placeholder='@user or ID',
            required=True,
            max_length=100
        )

        self.giving = TextInput(
            label='What are you giving?',
            placeholder='Example: 200M',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.receiving = TextInput(
            label='What is the other trader giving?',
            placeholder='Example: 500 Robux',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.both_join = TextInput(
            label='Can both users join links?',
            placeholder='YES or NO',
            required=True,
            max_length=10
        )

        self.tip = TextInput(
            label='Will you tip the MM?',
            placeholder='Optional',
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
            await create_ticket_with_details(
                interaction.guild, 
                interaction.user, 
                self.tier,
                self.trader.value,
                self.giving.value,
                self.receiving.value,
                self.both_join.value,
                self.tip.value if self.tip.value else 'None'
            )
            await interaction.followup.send('✅ Middleman ticket created! Check the ticket channel.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ Error creating ticket: {str(e)}', ephemeral=True)

# Tier Selection Dropdown - UPDATED
class TierSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label='0-150M Middleman',
                description='Trades up to 150M',
                value='basic',
                emoji='🟢'
            ),
            discord.SelectOption(
                label='150-500M Middleman',
                description='Trades between 150M-500M',
                value='advanced',
                emoji='🔵'
            ),
            discord.SelectOption(
                label='500M+ Middleman',
                description='Trades above 500M',
                value='premium',
                emoji='🟣'
            ),
            discord.SelectOption(
                label='OG Middleman',
                description='Any Value Trades',
                value='og',
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
        
        try:
            await interaction.message.delete()
        except:
            pass

class TierSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TierSelect())

# MM Ticket View
class MMTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='✅ Claim Ticket', style=discord.ButtonStyle.success, custom_id='claim_mm_ticket')
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        # Get all MM role IDs
        mm_role_ids = list(MM_ROLE_IDS.values())
        
        user_role_ids = [role.id for role in interaction.user.roles]
        is_mm = any(role_id in user_role_ids for role_id in mm_role_ids)
        is_admin = interaction.user.guild_permissions.administrator
        
        if not is_mm and not is_admin:
            return await interaction.response.send_message('❌ Only middlemen or administrators can claim tickets!', ephemeral=True)
        
        if interaction.channel.id in claimed_tickets:
            claimer_id = claimed_tickets[interaction.channel.id]
            claimer = interaction.guild.get_member(claimer_id)
            return await interaction.response.send_message(f'❌ This ticket is already claimed by {claimer.mention if claimer else "someone"}!', ephemeral=True)
        
        claimed_tickets[interaction.channel.id] = interaction.user.id
        
        ticket_data = active_tickets.get(interaction.channel.id)
        ticket_creator_id = ticket_data.get('user_id') if ticket_data else None
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
            description=f'✅ Ticket claimed by {interaction.user.mention}\n\n🔒 **Only the claimer and ticket creator can now send messages.**',
            color=0x57F287
        )
        embed.timestamp = datetime.utcnow()
        
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
    
    bot.add_view(TierSelectView())
    bot.add_view(MMTicketView())
    
    load_data()

# Setup Command
@bot.command(name='mmsetup')
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Create MM ticket panel"""
    embed = discord.Embed(
        title='⚖️ Middleman Services',
        description='Click the button below to open a middleman ticket.\n\n**Available Tiers:**\n🟢 **0-150M** - Trades up to 150m\n🔵 **150-500M** - Trades Up To 500m\n🟣 **500M+** - Trades Above 500m\n💎 **OG Middleman** - Og Trades Only',
        color=MM_COLOR
    )
    embed.set_footer(text='Select your tier to get started')
    embed.timestamp = datetime.utcnow()
    
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
    
    await ctx.send(embed=embed, view=view)
    await ctx.reply('✅ MM panel created successfully!')

# Claim Command
@bot.command(name='claim')
async def claim(ctx):
    """Claim a ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if ctx.channel.id in claimed_tickets:
        return await ctx.reply('❌ This ticket is already claimed!')

    claimed_tickets[ctx.channel.id] = ctx.author.id
    
    ticket_data = active_tickets.get(ctx.channel.id)
    ticket_creator_id = ticket_data.get('user_id') if ticket_data else None
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

# Close Command
@bot.command(name='close')
async def close_command(ctx):
    """Close a ticket"""
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
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been added to the ticket',
        color=0x57F287
    )
    embed.timestamp = datetime.utcnow()

    await ctx.reply(embed=embed)

@bot.command(name='remove')
async def remove_user(ctx, member: discord.Member = None):
    """Remove user from ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if not member:
        return await ctx.reply('❌ Please mention a valid user!')

    await ctx.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        description=f'✅ {member.mention} has been removed from the ticket',
        color=0x57F287
    )
    embed.timestamp = datetime.utcnow()

    await ctx.reply(embed=embed)

# Proof Command
@bot.command(name='proof')
async def proof_command(ctx):
    """Send MM proof to proof channel"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in a ticket.')

    ticket = active_tickets.get(ctx.channel.id)
    if not ticket:
        return await ctx.reply('❌ No ticket data found.')

    requester = ctx.guild.get_member(ticket['user_id'])
    trader = ticket.get('trader', 'Unknown')
    giving = ticket.get('giving', 'Unknown')
    receiving = ticket.get('receiving', 'Unknown')
    tier = ticket.get('tier', 'Unknown')

    # CHANGE THIS TO YOUR PROOF CHANNEL ID
    PROOF_CHANNEL_ID = 1458163922262560840
    proof_channel = ctx.guild.get_channel(PROOF_CHANNEL_ID)

    if not proof_channel:
        return await ctx.reply('❌ Proof channel not found.')

    embed = discord.Embed(
        title='✅ Trade Completed',
        color=0x57F287
    )

    embed.add_field(name='Middleman', value=ctx.author.mention, inline=False)
    embed.add_field(name='Tier', value=MM_TIERS[tier]['name'], inline=False)
    embed.add_field(name='Requester', value=requester.mention if requester else 'Unknown', inline=False)
    embed.add_field(name='Trader', value=trader, inline=False)
    embed.add_field(name='Gave', value=giving, inline=False)
    embed.add_field(name='Received', value=receiving, inline=False)

    ticket_number = ctx.channel.name.replace('ticket-', '')
    embed.set_footer(text=f"Ticket #{ticket_number}")

    await proof_channel.send(embed=embed)
    await ctx.reply('✅ Proof sent successfully!')

# Helper Functions
async def create_ticket_with_details(guild, user, tier, trader, giving, receiving, both_join, tip):
    """Create MM ticket"""
    try:
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY)
        
        mm_role_ids = list(MM_ROLE_IDS.values())
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=True, 
                read_message_history=True,
                mention_everyone=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }
        
        for role_id in mm_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
        
        ticket_channel = await guild.create_text_channel(
            name=f'ticket-{user.name}-mm',
            category=category,
            overwrites=overwrites
        )
        
        active_tickets[ticket_channel.id] = {
            'user_id': user.id,
            'created_at': datetime.utcnow().isoformat(),
            'tier': tier,
            'trader': trader,
            'giving': giving,
            'receiving': receiving,
            'both_join': both_join,
            'tip': tip
        }
        
        tier_role_id = MM_ROLE_IDS.get(tier)
        tier_role = guild.get_role(tier_role_id) if tier_role_id else None
        
        if tier_role:
            ping_message = f"{tier_role.mention} - New {MM_TIERS[tier]['name']} ticket opened!"
            await ticket_channel.send(ping_message, allowed_mentions=discord.AllowedMentions(roles=True))

        embed = discord.Embed(
            title=f"⚖️ {MM_TIERS[tier]['name']} Ticket",
            color=MM_COLOR
        )
        embed.set_footer(text=f'Ticket created by {user}', icon_url=user.display_avatar.url)
        embed.timestamp = datetime.utcnow()
        
        await ticket_channel.send(content=user.mention, embed=embed)
        
        details_embed = discord.Embed(
            title='📋 Middleman Trade Request',
            description=f'**Selected Tier:** {MM_TIERS[tier]["name"]}\n**Range:** {MM_TIERS[tier]["range"]}',
            color=MM_COLOR
        )
        
        details_embed.add_field(name='Trading With', value=trader, inline=False)
        details_embed.add_field(name='Requester Giving', value=giving, inline=False)
        details_embed.add_field(name='Requester Receiving', value=receiving, inline=False)
        details_embed.add_field(name='Both Can Join Links?', value=both_join, inline=False)
        details_embed.add_field(name='Tip', value=tip, inline=False)
        
        details_embed.set_footer(text=f'Requested by {user}', icon_url=user.display_avatar.url)
        details_embed.timestamp = datetime.utcnow()
        
        await ticket_channel.send(embed=details_embed, view=MMTicketView())
        
    except Exception as e:
        print(f'[ERROR] MM Ticket creation failed: {e}')
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

    if channel.id in active_tickets:
        del active_tickets[channel.id]
    if channel.id in claimed_tickets:
        del claimed_tickets[channel.id]

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
