import sqlite3, pdb

def main():
	con = sqlite3.connect("spells.db")
	cursor = con.cursor()
	cursor.execute("PRAGMA foreign_keys = ON")

	cursor.execute("DROP TABLE IF EXISTS spell_table")

	# Make Table if Necessary
	sql = """
	CREATE TABLE IF NOT EXISTS spell_table (
	name TEXT NOT NULL CHECK (trim(name) != ''))
	"""
	cursor.execute(sql)

	with con:
		cursor.execute("INSERT INTO spell_table VALUES")


	pdb.set_trace()



if __name__ == '__main__':
	main()