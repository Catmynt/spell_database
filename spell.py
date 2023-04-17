# spell.py
# For Quick and Easy D&D Spell Lookup / Filtering
# Nicklaus Auen

from fuzzywuzzy import fuzz, process
from bs4 import BeautifulSoup
from time import sleep
from tqdm import tqdm

import requests as rq
import sqlite3 as sql
import pickle as pkl
import textwrap, unidecode
import argparse, json, re, os, pdb

### Note: text wrapping and table displays still need work

ROOT = os.path.dirname(os.path.abspath(__file__))

CONFIDENCE_THRESHOLD = 90

# Terminal Dimensions
cols, rows = os.get_terminal_size()

# Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument('spell', help='the spell to be searched for', nargs='*', type=str)
parser.add_argument('-i', '--initialize', help='deletes the database and remakes it', action='store_true')
parser.add_argument('-s', '--sql', help='allows for execution of SQL queries', action='store_true')
parser.add_argument('-p', '--python', help='interactive mode', action='store_true')
parser.add_argument('-n', '--name', help='name of spell contains [word]', type=str)
parser.add_argument('-c', '--contains', help='description of spell contains [phrase]', nargs='*', type=str)
parser.add_argument('-t', '--test', help='test function for repeated calls', action='store_true')


def main(args):
	# Connect to DB
	connection = sql.connect("spells.db")
	cursor = connection.cursor()

	# Delete and Remake Database from spells.pkl
	if args.initialize:
		init(connection)
		extract_and_add(connection, load())
		print('Database successfully recreated.')
		return

	# Perform SQL Query
	if args.sql:
		while True:
			query = input("> ")

			if query == 'q':
				return

			cursor.execute(query)
			print(cursor.fetchall())

	if args.test:
		return
		
	# Keyword(s) in spell description
	if args.contains:
		name = ' '.join(args.contains)

		names = cursor.execute(f"SELECT name FROM spells WHERE description LIKE '%{name}%'")
		names = cursor.fetchall()

		print('\t', end='')
		print('\n\t'.join([a[0] for a in names]))
		return

	# Keyword(s) in spell name
	if args.name:
		name = args.name

		names = cursor.execute("SELECT name FROM spells")
		names = cursor.fetchall()

		names = [a[0] for a in names if name.lower() in a[0].lower()]
		names[0] = "\t" + names[0]

		print("\n\t".join(names))
		return

	if args.python:
		pdb.set_trace()
		return

	# Spell Lookup from Name (args.spell)

	# Foreign Key Fix
	cursor.execute('PRAGMA foreign_keys = ON')

	# Spell Name
	name = ' '.join(args.spell)

	# Fuzzy Match
	predicted = process.extractOne(name, get_spell_names(connection))

	# Confidence Check
	if predicted[-1] < CONFIDENCE_THRESHOLD:
		print(f'Invalid Spell ({name})')
		return

	# Fetch Spell Data for Display
	data = fetch(connection, predicted[0])

	# Invalid Spell Name
	if not data:
		print(f'Invalid Spell ({name})')
		return

	# Output
	display(data)


def get_spell_names(connection):
	'''Returns list of all spell names current in the database'''
	cursor = connection.cursor()
	cursor.execute("SELECT LOWER(name) FROM spells")
	return [a[0] for a in cursor.fetchall()]


def fetch(connection, name):
	'''Gets a spell from the table using its name'''
	cursor = connection.cursor()

	cursor.execute(f"""SELECT * FROM spells WHERE LOWER(name)=LOWER("{name}") """)

	spell_data = cursor.fetchone()

	# Spell Doesn't Exist
	if not spell_data:
		return None

	# Column Names
	columns = connection.cursor().execute("PRAGMA table_info('spells')").fetchall()
	columns = [a[1] for a in columns]

	return {c:s for c, s in zip(columns, spell_data)}


def display(spell_data):
	'''Prints spell_data in a nice format'''
	degrees = {1:'st', 2:'nd', 3:'rd'}

	output = []

	print(f"\n{spell_data['name']}") # Spell Name
	
	# Spell Level
	if spell_data['level'] != 0:
		print(f"\033[1m{spell_data['level']}{degrees.get(spell_data['level'], 'th')}-level {spell_data['school']}\033[0m")
	else:
		print(f"\033[1m{spell_data['school']} cantrip\033[0m")

	print(f"\n\033[1mCasting Time: {spell_data['casting_time']}\033[0m") # Casting TIme
	print(f"\033[1mRange: {spell_data['s_range']}\033[0m") # Range

	components = []

	# Components
	if spell_data['verbal']:
		components.append('V')
	if spell_data['somatic']:
		components.append('S')
	if spell_data['material']:
		components.extend(['M', f" ({spell_data['material_components']})"])

	print(textwrap.fill(f"\033[1mComponents: {', '.join(components[:-1]) + components[-1]}\033[0m", cols)) # improve later, join doesn't format correctly w variable components
	print(f"\033[1mDuration: {spell_data['duration']}\033[0m") # Duration
	print()

	for line in json.loads(spell_data['description']): # doing this instead of a list comprehension for textwrap purposes
		print(textwrap.fill(line.lstrip(), cols, replace_whitespace=False))

		# Bulleted List Formatting Fix
		if not line[0] == '*':
			print("")
	
	# Table Handling
	if spell_data['tables'] != "[]":
		print(json.loads(spell_data['tables']))

	print(f"\033[1mSpell Lists: {textwrap.fill(', '.join(json.loads(spell_data['spell_lists'])), cols)}\033[0m") # Spell lists
	print(f"\033[1mSource: {textwrap.fill(spell_data['source'], cols)}\033[0m") # Source book


def init(connection):
	'''Initializes the table for the first time'''
	cursor = connection.cursor()
	cursor.execute('DROP TABLE IF EXISTS spells')

	table = """
		CREATE TABLE IF NOT EXISTS spells (
		name text PRIMARY KEY NOT NULL CHECK (TRIM (name, ' ') != ''),
		level integer NOT NULL CHECK (level > -1),
		school text NOT NULL CHECK (TRIM (school, ' ') != ''),
		source text NOT NULL CHECK (TRIM (source, ' ') != ''),
		casting_time text NOT NULL CHECK (TRIM (casting_time, ' ') != ''),
		s_range text NOT NULL CHECK (TRIM (s_range, ' ') != ''),
		verbal bool NOT NULL,
		somatic bool NOT NULL,
		material bool NOT NULL,
		material_components text,
		duration text NOT NULL CHECK (TRIM (duration, ' ') != ''),
		description blob,
		tables blob,
		spell_lists blob 
		)
	"""
	cursor.execute(table)
	connection.commit()


def update(connection):
	'''Get Full Spelllist from Sitemap'''

	# Get Currently Known Spells
	'''Will eventually only get new spells'''

	# Use Sitemap to Get All Spells
	bloop = rq.get(f'https://dnd5e.wikidot.com/sitemap.xml').text

	# Soupify
	soup = BeautifulSoup(bloop, "lxml")

	# Extract Spell List
	spells = soup.find_all("loc")
	spells = [a.text[a.text.rindex(':')+1:] for a in spells if 'spell:' in a.text]

	return spells


def scrape(spell_list):
	'''Scrapes wikidot using the spell_list gained from the 
	sitemap and downloads every spell's information.'''
	
	link = 'http://dnd5e.wikidot.com/spell:'

	spell_info = []

	# Scrape
	for i in trange(len(spell_list)):
		# Get
		bloop = rq.get(f'{link}{spell_list[i]}').text

		# Save Content
		spell_info.append(bloop)

		# Sleep to Be Kind Regarding Rate of Requests
		sleep(0.3)

	return spell_info


def extract_and_add(connection, raw_spells):
	'''Extracts Relevant Spell Information from Raw HTML(s) and adds it to the spells table'''
	cursor = connection.cursor()	

	# Allow for single and multiple spell extraction
	if isinstance(raw_spells, str):
		raw_spells = [raw_spells]

	for raw_spell in tqdm(raw_spells):
		soup = BeautifulSoup(raw_spell, 'lxml')
		name = soup.find('title').text
		name = name[:name.index(' - ')]

		# Content Jumble
		content = soup.find('div', {'id':'page-content'})
		content = [a for a in content if a not in ['','\n']][1:-1]

		# Begin Unjumbling
		source = content[0].text
		source = source[8:] # cuts out 'Source: '

		# Cantrip Handling
		line = content[1].text

		if 'cantrip' in line.lower():
			level = 0
			school = line.split(' ')[0]
		else:
			level = line[0]
			school = ' '.join(line.split(' ')[1:])

		try:
			casting_time, s_range, components, duration = content[2].text.split('\n')
		except:
			# print(f"\t{name} has problems.")
			continue
		casting_time, s_range, components, duration = casting_time[14:], s_range[7:], components[12:], duration[10:]

		verbal = 'V' in components
		somatic = 'S' in components
		material = 'M' in components

		material_components = re.search("(?<=\()(.*?)(?=\))", components) if material else None
		material_components = material_components[0] if material_components else None

		description = []
		tables = []

		# Actual Content
		for i, p in enumerate(content[3:]):
			# Check if Spell List
			if 'Spell Lists' in p.text:
				spell_lists = p.text[13:]
				spell_lists = spell_lists.split(', ')
				continue

			# Check if Table
			if '<table' in str(p):
				# Extract Table Data
				table = [a.strip().split('\n') for a in p.text.split('\n\n\n') if a]
				
				# Add to tables
				tables.append(table)

			else:
				# Denote Bolded Terms with '*'
				paragraph = re.sub(r'<.?em>', '*', str(p))

				# Add Bullets to Bulleted Lists
				paragraph = paragraph.replace("<li>", "* ")

				# Remove Remaining HTML Tags / Unicode Artifacts
				paragraph = unidecode.unidecode(re.sub('<.*?>', '', paragraph))

				paragraph = paragraph.replace("*At Higher Levels.* ", "\033[1mAt Higher Levels.\033[0m\n")

				description.append(paragraph)


		# Check for Duplicates, Skip if Found (Flame Strike (UA) is the bane of my existence)
		if fetch(connection, name):
			continue

		# Add Spell to Table
		query = "INSERT INTO spells (name, level, school, source, casting_time, s_range, verbal, somatic, material, material_components, duration, description, tables, spell_lists) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
		cursor.execute(query, (name, level, school, source, casting_time, s_range, verbal, somatic, material, material_components, duration, json.dumps(description), json.dumps(tables), json.dumps(spell_lists)))
		connection.commit()
	

def save(spells):
	'''Saves the spell list into spells.pkl.'''
	with open(os.path.join(ROOT, "spells.pkl"), "wb") as f:
		pkl.dump(spells, f)


def load():
	'''Loads the spell list from spells.pkl.'''
	with open(os.path.join(ROOT, "spells.pkl"), "rb") as f:
		spells = pkl.load(f)

	return spells


def wprint(text):
	'''Textwraps the given text so that it fits nicely in the terminal.'''
	if isinstance(text, str):
		text = text.split()

	cpos = 0
	out = []

	for word in text:
		cpos += len(word)
		if cpos >= cols and "\n" not in word:
			out.append(f"\n{word}")
			cpos = 0
		else:
			out.append(word)

	for word in out:
		print(word, end=" ")


def save_html(spells):
	'''Saves one or more spells as an html file'''
	for spell in spells:
		soup = BeautifulSoup(spell, 'lxml')
		name = soup.find('title').text
		name = re.sub('/','_',name[:name.index(' - ')])
		with open(os.path.join(ROOT, "htmls", f"{name}.html"), 'w') as f:
			f.write(spell)


if __name__ == '__main__':
	main(parser.parse_args())


