import json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import SharedFunctions
import GlobalStore


class Command(CommandTemplate):
	triggers = ['generate', 'gen']
	helptext = "Generate random stories or words. Call a specific generator with '{commandPrefix}generate [genName]'. Available generators: "

	generators = {}
	filesLocation = os.path.join(GlobalStore.scriptfolder, "data", "generators")

	def onStart(self):
		# Set in 'onStart' so referencing the methods actually works
		self.generators = {"creature": self.generateCreature, "name": self.generateName, "SamAndMax": self.generateSamAndMaxSentence,
						   "word": self.generateWord, "word2": self.generateWord2}
		self.helptext += ", ".join(sorted(self.generators.keys()))

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		generator = None
		extraArgument = None
		if message.messagePartsLength > 0:
			requestedGeneratorName = message.messageParts[0].lower()
			# Check if the provided argument is an existing generator (in a case-insensitive manner)
			for generatorName in self.generators.keys():
				if generatorName.lower() == requestedGeneratorName:
					generator = generatorName
					break
		# If no generator was found, use a random one
		if not generator:
			generator = random.choice(self.generators.keys())
			if message.messagePartsLength > 0:
				extraArgument = message.messageParts[-1].lower()
		else:
			if message.messagePartsLength > 1:
				extraArgument = message.messageParts[-1].lower()

		#Say the text randomly generated by the selected generator
		generatedMessage = self.generators[generator](extraArgument)
		message.bot.sendMessage(message.source, generatedMessage)

	def getRandomLine(self, filelocation, filename):
		return SharedFunctions.getRandomLineFromFile(os.path.join(filelocation, filename))

	def numberToText(self, number):
		singleNumberNames = {0: u"zero", 1: u"one", 2: u"two", 3: u"three", 4: u"four", 5: u"five", 6: u"six", 7: u"seven",
							 8: u"eight", 9: u"nine", 10: u"ten", 11: u"eleven", 12: u"twelve", 13: u"thirteen",
							 14: u"fourteen", 15: u"fifteen", 16: u"sixteen", 17: u"seventeen", 18: u"eighteen", 19: u"nineteen"}
		if number in singleNumberNames:
			return singleNumberNames[number]
		else:
			#TODO: Handle numbers larger than 19 by combining words, like "twenty" and "two" for 22
			return unicode(number)

	def parseGrammarFile(self, grammarFilename, variableDict={}):
		with open(os.path.join(GlobalStore.scriptfolder, "data", "generators", grammarFilename), "r") as grammarfile:
			grammar = json.load(grammarfile)
		sentence = grammar["_start"]
		optionSeparator = u"|"
		tagFinderPattern = re.compile(r"<(.+?)>", re.UNICODE)
		while True:
			replacement = u""
			tagmatch = tagFinderPattern.search(sentence)
			if not tagmatch:
				break
			field = tagmatch.group(1)

			#Special commands start with an underscore
			if field.startswith(u"_"):
				arguments = field.split(optionSeparator)
				if field.startswith(u"_randint"):
					value = random.randint(int(arguments[1]), int(arguments[2]))
					if arguments[0] == u"_randint":
						replacement = unicode(value)
					elif arguments[0] == u"_randintasword":
						replacement = self.numberToText(value)
				elif field.startswith(u"_file"):
					#Load a sentence from the specified file. Useful for not cluttering up the grammar file with a lot of options
					newFilename = field.split(optionSeparator)[1]
					replacement = SharedFunctions.getRandomLineFromFile(newFilename)
				elif field.startswith(u"_variable"):
					#Variable, fill it in if it's in the variable dictionary
					if arguments[1] not in variableDict:
						return u"Error: Referenced undefined variable '{}'".format(arguments[1])
					else:
						replacement = variableDict[arguments[1]]
				else:
					return u"Error: Unknown command '{}' found!".format(field)
			#No command, so check if it's a valid key
			elif field not in grammar:
				return u"Error: Field '{}' not found in grammar file!".format(field)
			#All's well, fill it in
			else:
				if isinstance(grammar[field], list):
					#It's a list! Just pick a random entry
					replacement = random.choice(grammar[field])
				elif isinstance(grammar[field], dict):
					#Dictionary! The keys are chance percentages, the values are the replacement strings
					roll = random.randint(1, 100)
					for chance in sorted(grammar[field].keys()):
						if roll <= int(chance):
							replacement = grammar[field][chance]
							break
				elif isinstance(grammar[field], basestring):
					#If it's a string, just dump it in
					replacement = grammar[field]
				else:
					return u"Error: No handling defined for type '{}' found in field '{}'".format(type(grammar[field]), field)

			sentence = sentence.replace("<{}>".format(field), replacement, 1).strip()
		#Exited from loop, return the fully filled-in sentence
		return sentence


	def generateName(self, extraArgument):
		# First get a last name
		lastName = self.getRandomLine(self.filesLocation, "LastNames.txt")
		firstName = None
		gender = u"f"
		#Pick between a male and female first name
		if extraArgument in ["female", "f", "woman", "girl"]:
			gender = u"f"
		elif extraArgument in ["male", "m", "man", "boy"]:
			gender = u"m"
		elif random.randint(1, 100) <= 50:
			gender = u"f"
		else:
			gender = u"m"

		if gender == u"f":
			firstName = self.getRandomLine(self.filesLocation, "FirstNamesFemale.txt")
		else:
			firstName = self.getRandomLine(self.filesLocation, "FirstNamesMale.txt")
		return u"{} {}".format(firstName, lastName)


	def generateCreature(self, extraArgument):
		return self.parseGrammarFile("CreatureGenerator.grammar")


	def generateSamAndMaxSentence(self, extraArgument):
		basefilename = os.path.join(self.filesLocation, "SamAndMax")

		# With a small chance, pick an existing saying
		if extraArgument == u"original" or random.randint(1, 100) <= 5:
			return self.getRandomLine(basefilename, "OriginalSentences.txt")
		#Construct an original sentence
		else:
			sentence = self.parseGrammarFile("SamsSurprises.grammar")
			sentence = sentence[0].upper() + sentence[1:]
			return sentence


	def generateWord(self, extraArgument):
		"""Generate a word by putting letters together in semi-random order. Based on an old mIRC script of mine"""
		# Initial set-up
		vowels = ['a', 'e', 'i', 'o', 'u']
		specialVowels = ['y']

		consonants = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
		specialConsonants = ['j', 'q', 'v', 'w', 'x', 'z']

		newLetterFraction = 5
		vowelChance = 50  #percent

		#Determine how many words we're going to have to generate
		repeats = 1
		if extraArgument:
			repeats = SharedFunctions.parseInt(extraArgument, 1, 1, 25)

		words = []
		for i in range(0, repeats):
			word = u""
			currentVowelChance = vowelChance
			currentNewLetterFraction = newLetterFraction
			consonantCount = 0
			while random.randint(0, currentNewLetterFraction) <= 6:
				if random.randint(1, 100) <= vowelChance:
					consonantCount = 0
					#vowel. Check if we're going to add a special or normal vowel
					if random.randint(1, 100) <= 10:
						word += random.choice(specialVowels)
						currentVowelChance -= 30
					else:
						word += random.choice(vowels)
						currentVowelChance -= 20
				else:
					consonantCount += 1
					#consonant, same deal
					if random.randint(1, 100) <= 25:
						word += random.choice(specialConsonants)
						currentVowelChance += 30
					else:
						word += random.choice(consonants)
						currentVowelChance += 20
					if consonantCount > 3:
						currentVowelChance = 100
				currentNewLetterFraction += 1

			#Enough letters added. Finish up
			word = word[0].upper() + word[1:]
			words.append(word)

		#Enough words generated, let's return the result
		return u", ".join(words)

	def generateWord2(self, extraArgument):
		"""Another method to generate a word. Based on a slightly more advanced method, from an old project of mine that didn't go anywhere"""

		#Initial set-up
		vowels = ['a', 'e', 'i', 'o', 'u']
		specialVowels = ['y']

		consonants = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
		specialConsonants = ['j', 'q', 'v', 'w', 'x', 'z']

		#Temporary, for testing and to prevent increased bloat
		#vowels.extend(specialVowels)
		#consonants.extend(specialConsonants)

		#A syllable consists of an optional onset, a nucleus, and an optional coda
		#Sources:
		# http://en.wikipedia.org/wiki/English_phonology#Phonotactics
		# http://en.wiktionary.org/wiki/Appendix:English_pronunciation
		onsets = ["ch", "pl", "bl", "cl", "gl", "pr", "br", "tr", "dr", "cr", "gr", "tw", "dw", "qu", "pu",
				  "fl", "sl", "fr", "thr", "shr", "wh", "sw",
				  "sp", "st", "sk", "sm", "sn", "sph", "spl", "spr", "str", "scr", "squ", "sm"]  #Plus the normal consonants
		nuclei = ["ai", "ay", "ea", "ee", "y", "oa", "au", "oi", "oo", "ou"]  #Plus the normal vowels
		codas = ["ch", "lp", "lb", "lt", "ld", "lch", "lg", "lk", "rp", "rb", "rt", "rd", "rch", "rk", "lf", "lth",
				 "lsh", "rf", "rth", "rs", "rsh", "lm", "ln", "rm", "rn", "rl", "mp", "nt", "nd", "nch", "nk", "mph",
				 "mth", "nth", "ngth", "ft", "sp", "st", "sk", "fth", "pt", "ct", "kt", "pth", "ghth", "tz", "dth",
				 "ks", "lpt", "lfth", "ltz", "lst", "lct", "lx","rmth", "rpt", "rtz", "rst", "rct","mpt", "dth",
				 "nct", "nx", "xth", "xt"]  #Plus normal consonants

		simpleLetterChance = 65  #percent, whether a single letter is chosen instead of an onset/nucleus/coda
		basicLetterChance = 75  #percent, whether a simple consonant/vowel is chosen over  a more rare one

		#Prevent unnecessary and ugly code repetition
		def basicOrSpecialLetter(basicLetters, specialLetters, basicChance):
			if random.randint(1, 100) <= basicChance:
				return random.choice(basicLetters)
			else:
				return random.choice(specialLetters)

		#Start the word
		repeats = 1
		if extraArgument:
			repeats = SharedFunctions.parseInt(extraArgument, 1, 1, 25)

		words = []
		for i in range(0, repeats):
			syllableCount = 2
			if random.randint(1, 100) <= 50:
				syllableCount -= 1
			if random.randint(1, 100) <= 35:
				syllableCount += 1

			word = u""
			for j in range(0, syllableCount):
				#In most cases, add an onset
				if random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += basicOrSpecialLetter(consonants, specialConsonants, basicLetterChance)
					else:
						word += random.choice(onsets)

				#Nucleus!
				if random.randint(1, 100) <= simpleLetterChance:
					word += basicOrSpecialLetter(vowels, specialVowels, basicLetterChance)
				else:
					word += random.choice(nuclei)

				#Add a coda in most cases (Always add it if this is the last syllable of the word and it'd be too short otherwise)
				if (j == syllableCount - 1 and len(word) < 3) or random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += basicOrSpecialLetter(consonants, specialConsonants, basicLetterChance)
					else:
						word += random.choice(codas)

			word = word[0].upper() + word[1:]
			words.append(word)

		return u", ".join(words)