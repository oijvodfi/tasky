import discord
import subprocess
from discord.ext import commands
import os
from dotenv import load_dotenv
import re
import json
from mailings import send_tasks_email
import datetime

load_dotenv()
TOKEN = os.getenv('TOKEN')
PREFIX = os.getenv('PREFIX')
ALLOWED_CHANNEL_ID = os.getenv('ALLOWED_CHANNEL_ID')

intents = discord.Intents.default()
intents.presences = True
intents.members = True
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

with open('config.json') as f:
    config = json.load(f)

users = config['users']
projects = config['projects']

@bot.event
async def on_ready():
    print("DiscoBot started | Looking tassty")

@bot.command()
async def mail(ctx):
    send_tasks_email()
    await ctx.send('Отчет отправлен на почту.')

@bot.command()
async def hello(ctx):
    await ctx.send("Приветствую", view=MainView())

# ГЛАВНОЕ МЕНЮ


class MainView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label='Задачи', style=discord.ButtonStyle.primary)
    async def working_menu_button(self,
                          interaction: discord.Interaction,
                          button: discord.ui.button):
        await interaction.response.edit_message(
            content="Выберите действие",
            view=WorkingView())
        
    @discord.ui.button(label='Расширенные возможности', style=discord.ButtonStyle.green)
    async def basic_menu_button(self,
                          interaction: discord.Interaction,
                          button: discord.ui.button):
        await interaction.response.edit_message(
            content="Выберите действие",
            view=BasicView())
        
    @discord.ui.button(label='Тег-менеджер', style=discord.ButtonStyle.green)
    async def tag_management_menu_button(self,
                          interaction: discord.Interaction,
                          button: discord.ui.button):
        await interaction.response.edit_message(
            content="Выберите действие",
            view=TagManagementView())
        
# КНОПКИ ПОДТВЕРЖДЕНИЯ (Да/Нет)


class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label='Да', style=discord.ButtonStyle.green)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.stop()

    @discord.ui.button(label='Нет', style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.stop()

# СОЗДАТЬ ЗАДАЧУ


class EnhancedCreateTaskButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Создать задачу', style=discord.ButtonStyle.success)
        self.task_description = None
        self.user_tag = None
        self.project_name = None

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите название для задачи")
        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        self.task_description = message.content

        # Запрос пользователя для назначения задачи
        view = ConfirmView()
        await interaction.followup.send("Хотите ли вы назначить эту задачу определенному пользователю?", view=view)
        await view.wait()
        if view.value:
            user_selection_view = TaskSelectUserView(users, self)
            await interaction.followup.send("Выберите пользователя, которому хотите назначить задачу", view=user_selection_view)
            await user_selection_view.wait()

        # Запрос проекта для задачи
        view = ConfirmView()    
        await interaction.followup.send("Хотите ли вы добавить задачу в проект?", view=view)
        await view.wait()
        if view.value:
            project_selection_view = TaskSelectProjectView(projects, self)
            await interaction.followup.send("Выберите проект для задачи", view=project_selection_view)
            await project_selection_view.wait()

        # Запрос даты завершения задачи
        view = ConfirmView()
        await interaction.followup.send("Хотите ли вы назначить дату завершения задачи?", view=view)
        await view.wait()
        due_date = None
        if view.value:
            await interaction.followup.send("Введите дату завершения задачи (в формате DD-MM-YYYY)")
            due_date_response = await self.wait_for_response(interaction)
            parsed_date = datetime.datetime.strptime(due_date_response, '%d-%m-%Y')
            due_date = parsed_date.strftime('%Y-%m-%d')

        task_command = ["task", "add", self.task_description]
        if self.user_tag:
            task_command.append(f"+{self.user_tag}")
        if self.project_name:
            task_command.append(f"project:{self.project_name}")
        if due_date:

            task_command.append(f"due:{due_date}")
        process = subprocess.run(task_command, capture_output=True, text=True)
        output = process.stdout
        task_id = output.split()[-1].rstrip('.')


        await interaction.followup.send(
    f'**Задача {task_id}** "{self.task_description}" \n'
    f'**Назначена пользователю -** {self.user_tag if self.user_tag else "не указано"}. \n'
    f'**Добавлена в проект -** {self.project_name if self.project_name else "не указано"}.\n'
    f'**Дата завершения -** {due_date if due_date else "не указана"}.\n'
)

    async def wait_for_response(self, interaction):
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        message = await bot.wait_for('message', check=check)
        return message.content

    async def wait_for_confirmation(self, interaction):
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.content.lower() in ['да', 'нет']

        message = await bot.wait_for('message', check=check)
        return message.content.lower() == 'да'
    
class TaskUserSelect(discord.ui.Select):
    def __init__(self, users, button):
        options = [
            discord.SelectOption(label=user['name'], value=user['id'])
            for user in users
        ]
        super().__init__(placeholder='Выберите пользователя', options=options)
        self.button = button

    async def callback(self, interaction: discord.Interaction):
        user_id = self.values[0]
        user = next((user for user in users if user['id'] == user_id), None)
        if user is None:
            await interaction.response.send_message('Пользователь не найден.')
        else:
            await interaction.response.send_message(f'Выбран пользователь')
        user_tag = ''.join(e if e.isalnum() else '_' for e in user['tag'])
        self.button.user_tag = user_tag
        self.view.stop()
    
class TaskProjectSelect(discord.ui.Select):
    def __init__(self, projects, button):
        options = [
            discord.SelectOption(label=project, value=project)
            for project in projects
        ]
        options.append(discord.SelectOption(label='Добавить новый проект'))
        super().__init__(placeholder='Выберите проект', options=options)
        self.button = button

    async def callback(self, interaction: discord.Interaction):
        selected_option = self.values[0]
        if selected_option == 'Добавить новый проект':
            await interaction.response.send_message("Введите название нового проекта")
            def check(m):
                return (
                    m.author.id == interaction.user.id
                    and m.channel.id == interaction.channel.id
                )
            message = await bot.wait_for('message', check=check)
            new_project = message.content
            projects.append(new_project)
            with open('config.json', 'w') as f:
                json.dump({'users': users, 'projects': projects}, f, indent=4)
            await interaction.followup.send(f'Проект "{new_project}" добавлен.')
            selected_option = new_project
        else:
            await interaction.response.send_message(f'Выбран проект')
            project_name = selected_option
        self.button.project_name = project_name
        self.view.stop()

class TaskSelectUserView(discord.ui.View):
    def __init__(self, users, button):
        super().__init__()
        self.add_item(TaskUserSelect(users, button))

class TaskSelectProjectView(discord.ui.View):
    def __init__(self, projects, button):
        super().__init__()
        self.add_item(TaskProjectSelect(projects, button))
                    
# ЗАВЕРШИТЬ ЗАДАЧУ


class DoneTaskButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Завершить задачу',
                         row=1,
                         custom_id='done_task',
                         style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите ID задачи для ЗАВЕРШЕНИЯ (неск. - через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_ids = message.content.strip().split()

        for task_id in task_ids:
            try:
                subprocess.run(
                    ["task", task_id, "done"], check=True)
            except subprocess.CalledProcessError:
                await interaction.followup.send(
                    f'Не удалось завершить задачу{task_id}'
                    'Проверьте ID задачи.')

        await interaction.followup.send(
            f'Задача {", ".join(task_ids)} завершена.')

# УДАЛЕНИЕ ЗАДАЧ


class DeleteTasksButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Удаление задач',
                         row=2, custom_id='delete_task',
                         style=discord.ButtonStyle.danger
                         )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите ID задачи для УДАЛЕНИЯ (неск. - через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_id = message.content

        confirm_view = ConfirmView()
        await interaction.followup.send(
            f'Вы уверены, что хотите удалить задачу {task_id}?', view=confirm_view)
        await confirm_view.wait()
        if confirm_view.value:
            task_ids = task_id.split()
            for task in task_ids:
                subprocess.run(["task", "rc.confirmation=no", task, "delete"])
            await interaction.followup.send(
                f'Задачи {task_id} удалены.')
        else:
            await interaction.followup.send(
                f'Удаление задачи {task_id} отменено.')

# СПИСОК ВСЕХ ЗАДАЧ


class ListTasksButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Все задачи проекта',
                         row=1,
                         custom_id='list_tasks',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        try:
            task_list = subprocess.check_output(
                ["task", "list"], stderr=subprocess.STDOUT)
            task_list = task_list.decode('utf-8')
            
            # Split the task_list into multiple chunks if it's too long
            chunks = [task_list[i:i + 1900] for i in range(0, len(task_list), 1900)]
            
            # Send each chunk as a separate message
            for chunk in chunks:
                await interaction.channel.send(f'```utf\n{chunk}\n```')
        except Exception as e:
            await interaction.response.send_message(f"На данный момент задач нет")
                
# МОИ ЗАДАЧИ


class MyTasksButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Мои задачи',
                         row=0,
                         custom_id='my_tasks',
                         style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        user_name = interaction.user.name
        user_tag = ''.join(e if e.isalnum() else '_' for e in user_name)
        tag_argument = "+{0}".format(user_tag)
        try:
            task_list = subprocess.check_output(
                ["task", tag_argument, "list"], stderr=subprocess.STDOUT)
            task_list = task_list.decode('utf-8')
            task_list = f'```\n{task_list}\n```'
            await interaction.response.send_message(
                f'Ваши задачи: {task_list}')
        except subprocess.CalledProcessError:
            await interaction.response.send_message(
                'У вас нет задач.')

# Выполненные задачи


class CompletedTasksButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Выполненные задачи',
                         row=1,
                         custom_id='completed_tasks',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        try:
            completed_tasks = subprocess.check_output(
                ["task", "completed"], stderr=subprocess.STDOUT)
            completed_tasks = completed_tasks.decode('utf-8')
            if completed_tasks.strip() == '':
                await interaction.response.send_message(
                    'К сожалению, ещё нет выполненных задач')
            else:
                chunks = [completed_tasks[i:i + 1900] for i in range(0, len(completed_tasks), 1900)]
                for chunk in chunks:
                    await interaction.channel.send(f'```\n{chunk}\n```')
        except subprocess.CalledProcessError:
            await interaction.response.send_message(
                'Произошла ошибка при получении списка выполненных задач. Похоже, список пуст')

# Добавить в проект


class ProjectSelect(discord.ui.Select):
    def __init__(self, task_id):
        options = [discord.SelectOption(label=project) for project in projects]
        options.append(discord.SelectOption(label='Добавить новый проект'))
        super().__init__(placeholder='Выберите проект', options=options)
        self.task_id = task_id

    async def callback(self, interaction: discord.Interaction):
        selected_option = self.values[0]
        if selected_option == 'Добавить новый проект':
            await interaction.response.send_message("Введите название нового проекта")
            def check(m):
                return (
                    m.author.id == interaction.user.id
                    and m.channel.id == interaction.channel.id
                )
            message = await bot.wait_for('message', check=check)
            new_project = message.content
            projects.append(new_project)
            # Сохранение нового проекта в файл
            with open('config.json', 'w') as f:
                json.dump({'users': users, 'projects': projects}, f, indent=4)
            await interaction.followup.send(f'Проект "{new_project}" добавлен.')
            selected_option = new_project
        else:
            await interaction.response.send_message(f'Выбран проект "{selected_option}"')
        project_name = selected_option
        
        if project_name != 'Добавить новый проект':
            subprocess.run(["task", self.task_id, "modify", "project:"+project_name])
            await interaction.followup.send(
                f'Задача {self.task_id} отправлена в проект {project_name}.')

class ProjectView(discord.ui.View):
    def __init__(self, task_id):
        super().__init__()
        self.add_item(ProjectSelect(task_id))

class AddProjectButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Добавить в проект',
                         row=0,
                         custom_id='add_project',
                         style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите ID задачи")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_id = message.content
        await interaction.followup.send("Теперь выберите проект", view=ProjectView(task_id))

# Добавить тег


class AddTagButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Добавить тег',
                         row=0,
                         custom_id='add_tag',
                         style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите ID задачи и тег (через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_id, tag = message.content.split()
        subprocess.run(["task", task_id, "modify", "+"+tag])
        await interaction.followup.send(
            f'Тег {tag} добавлен в задачу {task_id}.')

# Фильтр по проекту


class FilterByProjectButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Фильтр по проекту',
                         row=1,
                         custom_id='filter_by_project',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите интересующий проект")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        project_name = message.content.strip()

        try:
            task_list = subprocess.check_output(
                ["task", "list", "project:{}".format(project_name)],
                stderr=subprocess.STDOUT)
            task_list = task_list.decode('utf-8')
            task_list = f'```\n{task_list}\n```'
            await interaction.followup.send(
                f'Задачи в проекте {project_name}: \n{task_list}')
        except subprocess.CalledProcessError:
            await interaction.followup.send(
                'Нет задач в этом проекте.')

# Фильтр по тегу


class FilterByTagButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Фильтр по тегу',
                         row=1,
                         custom_id='filter_by_tag',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Введите интересующие теги, разделенные пробелами")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        tags = message.content.strip().split()

        task_list = ''
        for tag in tags:
            try:
                current_task_list = subprocess.check_output(
                    ["task", "list", "+{}".format(tag)],
                    stderr=subprocess.STDOUT)
                current_task_list = current_task_list.decode('utf-8')
                task_list += f'Задачи с тегом {tag}: \n```\n{current_task_list}\n```\n'
            except subprocess.CalledProcessError:
                task_list += f'Нет задач с тегом {tag}.\n'

        await interaction.followup.send(task_list)

# Удаление тега из задачи


class RemoveTagFromTaskButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Удалить тег из задачи',
                         row=0,
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите ID задачи и тег (через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_id, tag = message.content.split()
        subprocess.run(["task", task_id, "modify", "-"+tag])
        await interaction.followup.send(f'Тег {tag} удален из задачи {task_id}.')

 # Просмотр всех тегов в задаче


class ViewTagsInTaskButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Просмотреть теги в задаче',
                         row=1,
                         style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите ID задачи")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        task_id = message.content.strip()

        try:
            task_info = subprocess.check_output(["task", task_id, "info"], stderr=subprocess.STDOUT)
            task_info = task_info.decode('utf-8')
            # Извлечение тегов из информации о задаче
            tags_line = next((line for line in task_info.split('\n') if line.startswith('Tags')), None)
            if tags_line is not None:
                tags = ', '.join(tags_line.split()[1:])
                await interaction.followup.send(f'Теги в задаче {task_id}: {tags}')
            else:
                await interaction.followup.send(f'В задаче {task_id} нет тегов.')
        except subprocess.CalledProcessError:
            await interaction.followup.send('Не удалось получить информацию о задаче.')

# Просмотр всех тегов


class ViewAllTagsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Все теги проекта',
                         row=1,
                         style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        try:
            task_list = subprocess.check_output(["task", "export"], stderr=subprocess.STDOUT)
            tasks = json.loads(task_list)

            # Извлечение тегов из каждой задачи
            tags = set()
            for task in tasks:
                if 'tags' in task:
                    tags.update(task['tags'])

            if tags:
                await interaction.response.send_message(f'Все теги: {", ".join(tags)}')
            else:
                await interaction.response.send_message('На удивление, тут ещё нет тегов.')
        except subprocess.CalledProcessError:
            await interaction.response.send_message('Произошла какая-то ошибка при получении списка тегов.')

# Переименовывание тега


class RenameTagButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Сменить тег задачи',
                         row=0,
                         custom_id='rename_tag',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите старое и новое имя тега (через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        old_tag, new_tag = message.content.split()
        subprocess.run(["task", "tag:{0}".format(old_tag), "modify", "+"+new_tag, "-"+old_tag])
        await interaction.followup.send(
            f'Тег {old_tag} переименован в {new_tag}.')
        
# Удаление тега из всех задач:


class DeleteTagButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Удалить тег',
                         row=0,
                         custom_id='delete_tag',
                         style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите имя тега для удаления")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        tag = message.content
        subprocess.run(["task", "tag:{0}".format(tag), "modify", "-"+tag])
        await interaction.followup.send(
            f'Тег {tag} удален из всех задач.')

# Изменение приоритета задачи


class ChangePriorityButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Назначить приоритет",
                         row=0,
                         style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        view = PriorityView()
        await interaction.response.send_message("Выберите приоритет:", view=view)

class PriorityButton(discord.ui.Button):
    def __init__(self, label, priority):
        super().__init__(label=label,
                         row=0,
                         custom_id=f'priority_{priority}',
                         style=discord.ButtonStyle.primary)
        self.task_id = None
        self.priority = priority

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите ID задачи (неск. - через пробел)")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        self.task_id = message.content

        subprocess.run(["task", self.task_id, "modify", f"priority:{self.priority}"])
        await interaction.followup.send(
            f'Приоритет задачи {self.task_id} изменен на {self.priority}.')
        
class PriorityView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(PriorityButton("Низкий", "L"))
        self.add_item(PriorityButton("Средний", "M"))
        self.add_item(PriorityButton("Высокий", "H"))

# Установка даты завершения задачи
        
        
class ChangeDueDateButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Назначить дату завершения",
                         row=0,
                         style=discord.ButtonStyle.primary)
        self.task_id = None

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Введите ID задачи")

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
            )
        message = await bot.wait_for('message', check=check)
        self.task_id = message.content

        await interaction.followup.send("Введите новую дату завершения (в формате DD-MM-YYYY)")

        message = await bot.wait_for('message', check=check)
        new_due_date = message.content

        try:
            parsed_date = datetime.datetime.strptime(new_due_date, '%d-%m-%Y')
            formatted_date = parsed_date.strftime('%Y-%m-%d')
            subprocess.run(["task", self.task_id, "modify", f"due:{formatted_date}"])
            await interaction.followup.send(f'Дата завершения задачи {self.task_id} изменена на {new_due_date}.')
        except ValueError:
            await interaction.followup.send("Неверный формат даты. Введите дату в формате DD-MM-YYYY.")

# Кнопка назад

class BackButton1(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Назад',
                         row=2,
                         custom_id='back_button1',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=MainView())

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Назад',
                         row=3,
                         custom_id='back_button',
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=MainView())

# Представление кнопок


class WorkingView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(MyTasksButton())
        self.add_item(DoneTaskButton())
        self.add_item(BackButton1())

class BasicView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(EnhancedCreateTaskButton())
        self.add_item(DeleteTasksButton())
        self.add_item(ChangePriorityButton())
        self.add_item(ChangeDueDateButton())
        self.add_item(AddProjectButton())
        self.add_item(ListTasksButton())
        self.add_item(CompletedTasksButton())
        self.add_item(FilterByProjectButton())
        self.add_item(FilterByTagButton())
        self.add_item(BackButton())

class TagManagementView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(AddTagButton())
        self.add_item(RemoveTagFromTaskButton())
        self.add_item(ViewAllTagsButton())
        self.add_item(ViewTagsInTaskButton())
        self.add_item(RenameTagButton())
        self.add_item(DeleteTagButton())
        self.add_item(BackButton())

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith('!task '):
        command = message.content[6:]
        task_command = f"task {command}"

        if command.startswith('delete '):
            task_id = command.split()[1]
            delete_command = f"task {task_id} delete"

            try:
                proc = subprocess.Popen(delete_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                output, error = proc.communicate(input=b"y\n")

                if proc.returncode == 0:
                    await message.channel.send("Задача успешно удалена.")
                else:
                    await message.channel.send(f"Ошибка при удалении задачи: {error.decode('utf-8')}")

            except subprocess.CalledProcessError as e:
                await message.channel.send(f"Ошибка при выполнении команды: {e.output.decode('utf-8')}")

        elif command == 'list':
            try:
                task_list = subprocess.check_output(["task", "list"], stderr=subprocess.STDOUT)
                task_list = task_list.decode('utf-8')
                chunks = [task_list[i:i + 1500] for i in range(0, len(task_list), 1500)]
                for chunk in chunks:
                    await message.channel.send(f"```\n{chunk}\n```")
            
            except subprocess.CalledProcessError as e:
                await message.channel.send(f"Ошибка при отправке списка задач: {e.output.decode('utf-8')}")

        else:
            result = subprocess.run(task_command, capture_output=True, text=True, shell=True)
            if result.stdout:
                await message.channel.send(result.stdout)
            if result.stderr:
                await message.channel.send(result.stderr)

    else:
        await bot.process_commands(message)

bot.run(TOKEN)