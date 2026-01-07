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
PROOF_CHANNEL_ID = 1234567890  # CHANGE THIS TO YOUR PROOF CHANNEL ID

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Storage
active_tickets = {}
claimed_tickets = {}
mm_stats = {}

# Color
MM_COLOR = 0xFEE75C

# MM Tier definitions with hierarchy
MM_TIERS = {
    'basic': {
        'name': '0-150M Middleman',
        'range': '0-150M',
        'description': 'Trades under Dragon / Traited Garamas etc',
        'emoji': '🟢',
        'level': 1
    },
    'advanced': {
        'name': '150-500M Middleman',
        'range': '150M-500M',
        'description': 'Trades including Base Dragon / Mutated Garamas',
        'emoji': '🔵',
        'level': 2
    },
    'premium': {
        'name': '500M+ Middleman',
        'range': '500M+',
        'description': 'Trades including Mutated / Traited Dragons',
        'emoji': '🟣',
        'level': 3
    },
    'og': {
        'name': 'OG Middleman',
        'range': 'All Trades',
        'description': 'Trades including OG / Headless Horseman',
        'emoji': '💎',
        'level': 4
    }
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
        'claimed_tickets': claimed_tickets,
        'mm_stats': mm_stats
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
            mm_stats.update(data.get('mm_stats', {}))
        print('✅ Data loaded successfully!')
    except FileNotFoundError:
        print('⚠️ No saved data found, starting fresh.')
    except Exception as e:
        print(f'❌ Error loading data: {e}')

def can_see_tier(user_roles, ticket_tier):
    """Check if user with their roles can see a ticket of given tier"""
    user_role_ids = [role.id for role in user_roles]
    ticket_level = MM_TIERS[ticket_tier]['level']
    
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

# Tier Selection Dropdown
class TierSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label='0-150M Middleman',
                description='Trades under Dragon / Traited Garamas etc',
                value='basic',
                emoji='🟢'
            ),
            discord.SelectOption(
                label='150-500M Middleman',
                description='Trades including Base Dragon / Mutated Garamas',
                value='advanced',
                emoji='🔵'
            ),
            discord.SelectOption(
                label='500M+ Middleman',
                description='Trades including Mutated / Traited Dragons',
                value='premium',
                emoji='🟣'
            ),
            discord.SelectOption(
                label='OG Middleman',
                description='Trades including OG / Headless Horseman',
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
        # Get ticket tier
        ticket_data = active_tickets.get(interaction.channel.id)
        if not ticket_data:
            return await interaction.response.send_message('❌ Ticket data not found!', ephemeral=True)
        
        ticket_tier = ticket_data.get('tier')
        
        # Check if user can claim this tier
        if not can_see_tier(interaction.user.roles, ticket_tier) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message('❌ You do not have permission to claim this ticket tier!', ephemeral=True)
        
        # Check if already claimed
        if interaction.channel.id in claimed_tickets:
            claimer_id = claimed_tickets[interaction.channel.id]
            claimer = interaction.guild.get_member(claimer_id)
            return await interaction.response.send_message(f'❌ This ticket is already claimed by {claimer.mention if claimer else "someone"}!', ephemeral=True)
        
        claimed_tickets[interaction.channel.id] = interaction.user.id
        
        ticket_creator_id = ticket_data.get('user_id')
        ticket_creator = interaction.guild.get_member(ticket_creator_id) if ticket_creator_id else None
        
        # Update permissions - only claimer and creator can talk
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
        embed.timestamp = datetime.utcnow()
        
        await interaction.response.send_message(embed=embed)
        await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
        save_data()
    
    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_mm_ticket')
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await close_ticket(interaction.channel, interaction.user)

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
        # Check if user is one of the two players
        if interaction.user.id not in [self.user1.id, self.user2.id]:
            return await interaction.response.send_message('❌ You are not part of this coinflip!', ephemeral=True)
        
        # Check if user already chose
        if interaction.user.id in self.chosen_users:
            return await interaction.response.send_message('❌ You already made your choice!', ephemeral=True)
        
        # Assign choice
        if interaction.user.id == self.user1.id:
            self.user1_choice = 'heads'
        else:
            self.user2_choice = 'heads'
        
        self.chosen_users.append(interaction.user.id)
        
        # Disable the heads button
        button.disabled = True
        
        # Update embed
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
        
        # If both chosen, start the game
        if len(self.chosen_users) == 2:
            await asyncio.sleep(1)
            await self.start_coinflip(interaction)
    
    @discord.ui.button(label='Tails', emoji='🪙', style=discord.ButtonStyle.secondary, custom_id='tails_cf')
    async def tails_button(self, interaction: discord.Interaction, button: Button):
        # Check if user is one of the two players
        if interaction.user.id not in [self.user1.id, self.user2.id]:
            return await interaction.response.send_message('❌ You are not part of this coinflip!', ephemeral=True)
        
        # Check if user already chose
        if interaction.user.id in self.chosen_users:
            return await interaction.response.send_message('❌ You already made your choice!', ephemeral=True)
        
        # Assign choice
        if interaction.user.id == self.user1.id:
            self.user1_choice = 'tails'
        else:
            self.user2_choice = 'tails'
        
        self.chosen_users.append(interaction.user.id)
        
        # Disable the tails button
        button.disabled = True
        
        # Update embed
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
        
        # If both chosen, start the game
        if len(self.chosen_users) == 2:
            await asyncio.sleep(1)
            await self.start_coinflip(interaction)
    
    async def start_coinflip(self, interaction):
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        mode_text = f"First to {self.total_rounds}" if self.is_first_to else f"Best of {self.total_rounds}"
        
        # Starting embed
        start_embed = discord.Embed(
            title='🪙 Coinflip Starting!',
            description=f'**{self.user1.mention}** chose **{self.user1_choice.upper()}**\n**{self.user2.mention}** chose **{self.user2_choice.upper()}**\n\n**Mode:** {mode_text}',
            color=MM_COLOR
        )
        start_embed.timestamp = datetime.utcnow()
        
        await interaction.message.edit(embed=start_embed, view=self)
        await asyncio.sleep(2)
        
        # Play rounds
        user1_wins = 0
        user2_wins = 0
        rounds_played = 0
        results = []
        
        while rounds_played < self.total_rounds:
            flip_result = random.choice(['heads', 'tails'])
            rounds_played += 1
            
            if flip_result == self.user1_choice:
                user1_wins += 1
                results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user1.mention} wins! 🎉")
            else:
                user2_wins += 1
                results.append(f"Round {rounds_played}: **{flip_result.upper()}** - {self.user2.mention} wins! 🎉")
            
            # Check if someone won (first to mode)
            if self.is_first_to and (user1_wins >= self.total_rounds or user2_wins >= self.total_rounds):
                break
            
            # Update embed
            progress_embed = discord.Embed(
                title='🪙 Coinflip in Progress...',
                description=f'**{self.user1.mention}** ({self.user1_choice.upper()}): {user1_wins} wins\n**{self.user2.mention}** ({self.user2_choice.upper()}): {user2_wins} wins\n\n**Mode:** {mode_text}\n**Rounds Played:** {rounds_played}/{self.total_rounds}',
                color=0xFFA500
            )
            
            # Show last 5 results
            recent_results = '\n'.join(results[-5:])
            progress_embed.add_field(name='Recent Results', value=recent_results if recent_results else 'None yet', inline=False)
            progress_embed.timestamp = datetime.utcnow()
            
            await interaction.message.edit(embed=progress_embed, view=self)
            await asyncio.sleep(1.5)
        
        # Determine final winner
        if user1_wins > user2_wins:
            final_winner = self.user1
            final_color = 0x57F287
        elif user2_wins > user1_wins:
            final_winner = self.user2
            final_color = 0x57F287
        else:
            final_winner = None
            final_color = 0xFEE75C
        
        # Final embed
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
        
        # Show all results if not too many
        if rounds_played <= 10:
            all_results = '\n'.join(results)
            final_embed.add_field(name='All Results', value=all_results, inline=False)
        else:
            recent_results = '\n'.join(results[-10:])
            final_embed.add_field(name='Last 10 Results', value=recent_results, inline=False)
        
        final_embed.timestamp = datetime.utcnow()
        
        await interaction.message.edit(embed=final_embed, view=self)

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
        description='Click the button below to open a middleman ticket.\n\n**Available Tiers:**\n🟢 **0-150M** - Trades under Dragon / Traited Garamas etc\n🔵 **150-500M** - Trades including Base Dragon / Mutated Garamas\n🟣 **500M+** - Trades including Mutated / Traited Dragons\n💎 **OG** - Trades including OG / Headless Horseman',
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
    await ctx.message.delete()

# Claim Command
@bot.command(name='claim')
async def claim(ctx):
    """Claim a ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')

    if ctx.channel.id in claimed_tickets:
        return await ctx.reply('❌ This ticket is already claimed!')

    ticket_data = active_tickets.get(ctx.channel.id)
    if not ticket_data:
        return await ctx.reply('❌ Ticket data not found!')
    
    ticket_tier = ticket_data.get('tier')
    
    if not can_see_tier(ctx.author.roles, ticket_tier) and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ You do not have permission to claim this ticket tier!')

    claimed_tickets[ctx.channel.id] = ctx.author.id
    
    ticket_creator_id = ticket_data.get('user_id')
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
    save_data()

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
    embed.timestamp = datetime.utcnow()

    await proof_channel.send(embed=embed)
    
    # NEW: Track MM stats
    user_id_str = str(ctx.author.id)
    if user_id_str not in mm_stats:
        mm_stats[user_id_str] = 0
    mm_stats[user_id_str] += 1
    save_data()
    
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
        name='🪙 Fun Commands',
        value='`$cf @user1 vs @user2 [ft] <number>` - Coinflip game\n'
              'Examples:\n'
              '• `$cf @user1 vs @user2 ft 3` (First to 3)\n'
              '• `$cf user1 vs user2 5` (Best of 5)',
        inline=False
    )
    
    embed.set_footer(text='Use $help to see this message again')
    
    await ctx.reply(embed=embed)

# MM Stats Command
@bot.command(name='mmstats')
async def mmstats_command(ctx, member: discord.Member = None):
    """View MM statistics for a user"""
    target = member if member else ctx.author
    user_id_str = str(target.id)
    
    tickets_completed = mm_stats.get(user_id_str, 0)
    
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
    
    # Calculate rank
    sorted_stats = sorted(mm_stats.items(), key=lambda x: x[1], reverse=True)
    rank = next((i + 1 for i, (uid, _) in enumerate(sorted_stats) if uid == user_id_str), None)
    
    if rank:
        embed.add_field(
            name='🏆 Rank',
            value=f'#{rank} out of {len(mm_stats)} middlemen',
            inline=False
        )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.timestamp = datetime.utcnow()
    
    await ctx.reply(embed=embed)

# MM Leaderboard Command
@bot.command(name='mmleaderboard')
async def mmleaderboard_command(ctx):
    """View top middlemen leaderboard"""
    if not mm_stats:
        return await ctx.reply('❌ No middleman statistics available yet!')
    
    # Sort by tickets completed
    sorted_stats = sorted(mm_stats.items(), key=lambda x: x[1], reverse=True)
    
    embed = discord.Embed(
        title='🏆 Middleman Leaderboard',
        description='Top middlemen by completed tickets',
        color=MM_COLOR
    )
    
    # Show top 10
    leaderboard_text = []
    for i, (user_id, tickets) in enumerate(sorted_stats[:10], 1):
        member = ctx.guild.get_member(int(user_id))
        if member:
            medal = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            leaderboard_text.append(f'{medal} {member.mention} has completed **{tickets}** middleman tickets')
    
    if leaderboard_text:
        embed.description = '\n'.join(leaderboard_text)
    else:
        embed.description = 'No data available'
    
    embed.set_footer(text=f'Total Middlemen: {len(mm_stats)}')
    embed.timestamp = datetime.utcnow()
    
    await ctx.reply(embed=embed)

# Unclaim Command
@bot.command(name='unclaim')
async def unclaim_command(ctx):
    """Unclaim a ticket"""
    if not ctx.channel.name.startswith('ticket-'):
        return await ctx.reply('❌ This command can only be used in ticket channels!')
    
    if ctx.channel.id not in claimed_tickets:
        return await ctx.reply('❌ This ticket is not claimed!')
    
    claimer_id = claimed_tickets[ctx.channel.id]
    
    # Check if user is the claimer or has admin perms
    if ctx.author.id != claimer_id and not ctx.author.guild_permissions.administrator:
        return await ctx.reply('❌ Only the ticket claimer or administrators can unclaim this ticket!')
    
    # Get ticket data to restore proper permissions
    ticket_data = active_tickets.get(ctx.channel.id)
    if not ticket_data:
        return await ctx.reply('❌ Ticket data not found!')
    
    ticket_tier = ticket_data.get('tier')
    ticket_creator_id = ticket_data.get('user_id')
    ticket_creator = ctx.guild.get_member(ticket_creator_id) if ticket_creator_id else None
    
    # Remove claim
    del claimed_tickets[ctx.channel.id]
    
    # Restore permissions for all MM roles that can see this tier
    ticket_level = MM_TIERS[ticket_tier]['level']
    
    for tier_key, role_id in MM_ROLE_IDS.items():
        role = ctx.guild.get_role(role_id)
        if role:
            tier_level = MM_TIERS[tier_key]['level']
            if tier_key == 'og' or tier_level >= ticket_level:
                await ctx.channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
    
    # Reset channel name
    new_name = ctx.channel.name.replace('-claimed', '')
    await ctx.channel.edit(name=new_name)
    
    embed = discord.Embed(
        description=f'✅ Ticket unclaimed by {ctx.author.mention}\n\n🔓 **All eligible middlemen can now claim this ticket again.**',
        color=MM_COLOR
    )
    embed.timestamp = datetime.utcnow()
    
    await ctx.reply(embed=embed)
    save_data()

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
    embed.timestamp = datetime.utcnow()
    
    view = CoinflipView(user1, user2, total_rounds, is_first_to)
    await ctx.send(embed=embed, view=view)

# Helper Functions
async def create_ticket_with_details(guild, user, tier, trader, giving, receiving, both_join, tip):
    """Create MM ticket with tier-based permissions"""
    try:
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY)
        
        # Base overwrites
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
        
        # Add ONLY the roles that can see this tier
        ticket_level = MM_TIERS[tier]['level']
        
        for tier_key, role_id in MM_ROLE_IDS.items():
            role = guild.get_role(role_id)
            if role:
                tier_level = MM_TIERS[tier_key]['level']
                # OG sees everything, others only see their level or below
                if tier_key == 'og' or tier_level >= ticket_level:
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
        
        # Ping ONLY the specific tier role
        tier_role_id = MM_ROLE_IDS.get(tier)
        tier_role = guild.get_role(tier_role_id) if tier_role_id else None
        
        if tier_role:
            ping_message = f"{tier_role.mention} - New {MM_TIERS[tier]['name']} ticket opened!"
            await ticket_channel.send(ping_message, allowed_mentions=discord.AllowedMentions(roles=True))
        
        # Combined embed
        embed = discord.Embed(
            title=f"{MM_TIERS[tier]['emoji']} {MM_TIERS[tier]['name']}",
            description=f"Welcome {user.mention}!\n\nOur team will be with you shortly. Please wait for a middleman to claim this ticket.",
            color=MM_COLOR
        )
        
        embed.add_field(
            name="📊 Trade Details",
            value=f"**Range:** {MM_TIERS[tier]['range']}\n**Status:** 🟡 Waiting for Middleman",
            inline=False
        )
        
        embed.add_field(
            name="👥 Trading With",
            value=trader,
            inline=False
        )
        
        embed.add_field(
            name="📤 You're Giving",
            value=giving,
            inline=True
        )
        
        embed.add_field(
            name="📥 You're Receiving",
            value=receiving,
            inline=True
        )
        
        embed.add_field(
            name="🔗 Both Can Join Links?",
            value=both_join,
            inline=True
        )
        
        embed.add_field(
            name="💰 Tip",
            value=tip if tip else "None",
            inline=True
        )
        
        embed.set_footer(
            text=f'Ticket created by {user.name}',
            icon_url=user.display_avatar.url
        )
        embed.timestamp = datetime.utcnow()
        
        await ticket_channel.send(embed=embed, view=MMTicketView())
        save_data()
        
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
    
    save_data()

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
