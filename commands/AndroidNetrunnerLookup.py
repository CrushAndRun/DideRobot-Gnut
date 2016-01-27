import json, os, random, re, time
import HTMLParser

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['netrunner', 'net']
	helptext = "Looks up info on 'Android: Netrunner' cards. Provide a card name or regex to search for, or 'random' for a surprise. "
	helptext += "Or use the 'search' parameter with key-value attribute pairs for more control over the search."
	scheduledFunctionTime = 5.0 * 24.0 * 3600.0  #Every 5 days, because changes don't happen often
	callInThread = True

	areCardfilesBeingUpdated = False

	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateCardFile)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#Immediately check if there's any parameters, to prevent useless work
		if message.messagePartsLength == 0:
			message.bot.say(message.source, "Please provide a term to search for. See '{}help {}' for an explanation how to use this command".format(message.bot.factory.commandPrefix, message.trigger))
			return

		searchType = message.messageParts[0].lower()

		addExtendedInfo = message.trigger == 'netrunner'

		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		if searchType == 'update' or searchType == 'forceupdate':
			if self.areCardfilesBeingUpdated:
				replytext = "I'm already updating!"
			elif not message.bot.factory.isUserAdmin(message.user, message.userNickname, message.userAddress):
				replytext = "Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(searchType == 'forceupdate')[1]
				#Since we're checking now, set the automatic check to start counting from now on
				self.scheduledFunctionTimer.reset()
			message.bot.say(message.source, replytext)
			return

		#Check if the data file even exists
		elif not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'NetrunnerCards.json')):
			if self.areCardfilesBeingUpdated:
				replytext = "I don't have my card database, but I'm solving that problem as we speak! Try again in, oh,  10, 15 seconds"
			else:
				replytext = "Sorry, I don't appear to have my card database. I'll try to retrieve it though! Give me 20 seconds, tops"
				self.executeScheduledFunction()
				self.scheduledFunctionTimer.reset()
			message.bot.say(message.source, replytext)
			return

		#If we reached here, we're gonna search through the card store
		searchDict = {}
		# If there is an actual search (with colon key-value separator OR a random card is requested with specific search requirements
		if (searchType == 'search' and ':' in message.message) or (searchType == 'random' and message.messagePartsLength > 1):
			#Advanced search!
			if message.messagePartsLength <= 1:
				message.bot.say(message.source, "Please provide an advanced search query too, in JSON format, so 'key1: value1, key2: value2'")
				return

			#Turn the search string (not the argument) into a usable dictionary, case-insensitive,
			searchDict = SharedFunctions.stringToDict(" ".join(message.messageParts[1:]).lower(), True)
			if len(searchDict) == 0:
				message.bot.say(message.source, "That is not a valid search query. It should be entered like JSON, so 'name: Wall of Thorns, type: ICE,...'. ")
				return
		#If the searchtype is just 'random', don't set a 'name' field so we don't go through all the cards first
		#  Otherwise, set the whole message as the 'name' search, since that's the default search
		elif not searchType.startswith('random'):
			searchDict['title'] = message.message.lower()

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {'setname': ['set', 'sets'], 'flavor': ['flavour'], 'title': ['name']}
		for correctTerm, listOfWrongterms in searchTermsToCorrect.iteritems():
			for wrongTerm in listOfWrongterms:
				if wrongTerm in searchDict:
					if correctTerm not in searchDict:
						searchDict[correctTerm] = searchDict[wrongTerm]
					searchDict.pop(wrongTerm)

		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.iteritems():
			regex = None
			try:
				#Since the query is a string, and the card data is unicode, convert the query to unicode before turning it into a regex
				regex = re.compile(unicode(query, encoding='utf8'), re.IGNORECASE)
			except (re.error, SyntaxError) as e:
				self.logError("[Netrunner] Regex error when trying to parse '{}': {}".format(query, e))
				errors.append(attrib)
			except UnicodeDecodeError as e:
				self.logError("[Netrunner] Unicode error in key '{}': {}".format(attrib, e))
				errors.append(attrib)
			else:
				regexDict[attrib] = regex
		#If there were errors parsing the regular expressions, don't continue, to prevent errors further down
		if len(errors) > 0:
			#If there was only one search element to begin with, there's no need to specify
			if len(searchDict) == 1:
				replytext = "An error occurred when trying to parse your search query. Please check if it is a valid regular expression, and that there are no non-UTF8 characters"
			#If there were more elements but only one error, specify
			elif len(errors) == 1:
				replytext = "An error occurred while trying to parse the query for the '{}' field. Please check if it is a valid regular expression without non-UTF8 characters".format(errors[0])
			#Multiple errors, list them all
			else:
				replytext = "Errors occurred while parsing attributes: {}. Please check your search query for errors".format(", ".join(errors))
			message.bot.say(message.source, replytext)
			return

		#All entered data is valid, look through the stored cards
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'NetrunnerCards.json'), 'r') as jsonfile:
			cardstore = json.load(jsonfile)

		for index in xrange(0, len(cardstore)):
			carddata = cardstore.pop(0)

			#Then check if the rest of the attributes match
			for attrib in regexDict:
				if attrib not in carddata or not regexDict[attrib].search(carddata[attrib]):
					#If the wanted attribute is either not in the card, or it doesn't match, throw it out
					break
			#The else-block of a for-loop is executed when a for-loop isn't broken out of. So if everything matches, we get here
			else:
				cardstore.append(carddata)

		numberOfCardsFound = len(cardstore)
		#Pick a random card if needed and possible
		if searchType.startswith('random') and numberOfCardsFound > 0:
			cardstore = [random.choice(cardstore)]
			numberOfCardsFound = 1

		if numberOfCardsFound == 0:
			replytext = "Sorry, no card matching your query was found"
		elif numberOfCardsFound == 1:
			replytext = self.getFormattedCardInfo(cardstore[0], addExtendedInfo)
		else:
			nameMatchedCardFound = False
			replytext = ""
			#If there was a name search, check if the literal name is in the resulting cards
			if 'title' in searchDict:
				titleMatchIndex = None
				for index, card in enumerate(cardstore):
					if card['title'].lower() == searchDict['title']:
						titleMatchIndex = index
						break

				if titleMatchIndex:
					replytext = self.getFormattedCardInfo(cardstore[titleMatchIndex], addExtendedInfo)
					cardstore.pop(titleMatchIndex)
					numberOfCardsFound -= 1
					nameMatchedCardFound = True

			#Pick some cards to show
			maxCardsToList = 15
			if numberOfCardsFound > maxCardsToList:
				cardstore = random.sample(cardstore, maxCardsToList)
			cardnameText = ""
			for card in cardstore:
				cardnameText += card['title'].encode('utf-8') + "; "
			cardnameText = cardnameText[:-2]

			if nameMatchedCardFound:
				replytext += " ({:,} more match{} found: ".format(numberOfCardsFound, 'es' if numberOfCardsFound > 1 else '')
			else:
				replytext += "Your search returned {:,} cards: ".format(numberOfCardsFound)
			replytext += cardnameText
			if numberOfCardsFound > maxCardsToList:
				replytext += " and {:,} more".format(numberOfCardsFound - maxCardsToList)
			#Since the extra results list is bracketed when a literal match was also found, it needs a closing bracket
			if nameMatchedCardFound:
				replytext += ")"


		re.purge()  #Clear the stored regexes, since we don't need them anymore
		message.bot.say(message.source, replytext)

	@staticmethod
	def getFormattedCardInfo(card, addExtendedInfo=False):
		cardInfoList = [u'\x02' + card['title'] + u'\x0f']  #Make title bold
		if 'type' in card:
			cardInfoList.append(card['type'])
			if 'subtype' in card:
				cardInfoList[-1] += u": " + card['subtype']
		if 'cost' in card:
			cardInfoList.append(u"Costs " + card['cost'])
		if 'advancementcost' in card:
			cardInfoList.append(card['advancementcost'] + u" Advance Cost")
		if 'minimumdecksize' in card:
			cardInfoList.append(u"Min Deck Size: " + card['minimumdecksize'])
		if 'influencelimit' in card:
			cardInfoList.append(u"Influence Limit: " + card['influencelimit'])
		if 'baselink' in card:
			cardInfoList.append(u"Link Strength: " + card['baselink'])
		if 'agendapoints' in card:
			cardInfoList.append(u"Agenda Points: " + card['agendapoints'])
		if 'trash' in card:
			cardInfoList.append(u"Trash: " + card['trash'])
		if 'influence' in card:
			cardInfoList.append(u"Influence: " + card['influence'])
		if 'text' in card:
			cardInfoList.append(card['text'])
		if 'faction' in card:
			cardInfoList.append(u"Faction: " + card['faction'])
		if addExtendedInfo:
			if 'flavor' in card:
				cardInfoList.append(u"\x0314" + card['flavor'] + u"\x0f")  #Color flavor text gray
			if 'setname' in card:
				cardInfoList.append(u"in set " + card['setname'])

		#FILL THAT SHIT IN (encoded properly)
		separator = u' \x0314|\x0f '  #'\x03' is the 'color' control char, 14 is grey, and '\x0f' is the 'reset' character ending any decoration
		separatorLength = len(separator)
		#Keep adding parts to the output until an entire block wouldn't fit on one line, then start a new message
		replytext = u''
		messageLength = 0
		MAX_MESSAGE_LENGTH = 325

		while len(cardInfoList) > 0:
			cardInfoPart = cardInfoList.pop(0)
			partLength = len(cardInfoPart)
			if messageLength + partLength < MAX_MESSAGE_LENGTH:
				replytext += cardInfoPart
				messageLength += partLength
				#Separator!
				if messageLength + separatorLength > MAX_MESSAGE_LENGTH:
					#If the separator wouldn't fit anymore, start a new message
					replytext += '\n'
					messageLength = 0
				#Add a separator
				replytext += separator
				messageLength += separatorLength
			else:
				#If we would exceed max message length, cut off at the highest space and continue in a new message
				#  If the message started with a special character (bold for name, grey for flavour), copy those
				prefix = u''
				#bold
				if cardInfoPart.startswith(u'\x02'):
					prefix = u'\x02'
				#color
				elif cardInfoPart.startswith(u'\x03'):
					#Also copy colour code
					prefix = cardInfoPart[:3]
				#Get the spot in the text where the cut-off would be (How much of the part text fits in the open space)
				splitIndex = MAX_MESSAGE_LENGTH - messageLength
				#Then get the last space before that index, so we don't split mid-word (if possible)
				if u' ' in cardInfoPart[:splitIndex]:
					splitIndex = cardInfoPart.rindex(u' ', 0, splitIndex)
				#If we can't find a space, add a dash to indicate the word continues in the new message
				elif splitIndex > 0:
					cardInfoPart = cardInfoPart[:splitIndex-1] + u'-' + cardInfoPart[splitIndex-1:]
				#Add the second section back to the list, so it can be properly added, even if it would still be too long
				cardInfoList.insert(0, prefix + cardInfoPart[splitIndex:])
				#Then add the first part to the message
				replytext += cardInfoPart[:splitIndex] + u'\n'
				messageLength = 0

		#Remove the separator at the end, and make sure it's a string and not unicode
		replytext = replytext.rstrip(separator).rstrip().encode('utf-8')
		return replytext


	def updateCardFile(self, forceupdate=False):
		starttime = time.time()
		try:
			requestReply = requests.get("http://netrunnerdb.com/api/cards", timeout=60.0)
			carddata = json.loads(requestReply.text)
		except requests.exceptions.Timeout:
			self.logError("[Netrunner] Data retrieval took too long")
			return (False, "Card retrieval took too long")
		except ValueError:
			self.logError("[Netrunner] Invalid JSON when updating card database:", requestReply.text)
			return (False, "Invalid JSON data")

		#If we don't absolutely HAVE to update, check if our last update isn't too soon, to prevent work and traffic
		versionfilename = os.path.join(GlobalStore.scriptfolder, 'data', 'NetrunnerCardsVersion.json')
		if not forceupdate:
			if os.path.exists(versionfilename):
				with open(versionfilename) as versionfile:
					versiondata = json.load(versionfile)
				if time.time() - versiondata['lastUpdateTime'] < 5.0 * 24.0 * 3600.0:
					self.logInfo("[Netrunner] Not updating card database, last check less than 5 days ago")
					return (False, "Last update was less than 5 days ago, not updating now")

		self.areCardfilesBeingUpdated = True

		#Clean up the data a bit so it's smaller and easier to use
		keysToRemove = ('ancurLink', 'faction_code', 'faction_letter', 'imagesrc', 'last-modified', 'limited',
						'set_code', 'side_code', 'subtype_code', 'type_code', 'quantity', 'uniqueness', 'url')
		keysToMakeStrings = ('advancementcost', 'agendapoints', 'baselink', 'cost', 'cyclenumber', 'factioncost',
							 'influencelimit', 'memoryunits', 'minimumdecksize', 'number', 'quantity', 'strength', 'trash')
		keysToRename = {'factioncost': 'influence'}
		keysToReformat = ('flavor', 'text')
		keysToCheckForLength = ('flavor', 'subtype')
		htmlparser = HTMLParser.HTMLParser()  #Needed because for some reason there's HTML entities in the text ('&ndash' etc)
		for card in carddata:
			for keyToRemove in keysToRemove:
				if keyToRemove in card:
					del card[keyToRemove]

			for keyToMakeString in keysToMakeStrings:
				if keyToMakeString in card:
					card[keyToMakeString] = unicode(card[keyToMakeString])

			for keyToRename, newname in keysToRename.iteritems():
				if keyToRename in card:
					card[newname] = card[keyToRename]
					del card[keyToRename]

			for field in keysToReformat:
				if field in card:
					#Some fields have HTML tags for some reason, remove those
					card[field] = card[field].replace('<strong>', '').replace('</strong>', '').replace('<sup>', '').replace('</sup>', '')
					#Also remove newlines
					card[field] = card[field].replace('\r\n', ' ').replace('\n', ' ')
					#Fix stray HTML entities
					card[field] = htmlparser.unescape(card[field])

			for field in keysToCheckForLength:
				if field in card:
					#If the field is, remove it from the card
					if len(card[field]) == 0:
						del card[field]

		#Save the carddata to file
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'NetrunnerCards.json'), 'w') as cardfile:
			cardfile.write(json.dumps(carddata))  #Faster than 'json.dump()' for some reason
		#Update the last-updated date
		with open(versionfilename, 'w') as versionfile:
			versionfile.write(json.dumps({'lastUpdateTime': time.time()}))

		#Done! Free the file read, log the update, and report our success
		self.areCardfilesBeingUpdated = False
		self.logInfo("[NetRunner] Updating cards took {} seconds".format(time.time() - starttime))
		return (True, "Netrunner card database successfully updated")