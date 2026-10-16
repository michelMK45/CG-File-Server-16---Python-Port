frTourn = -1
gloTourn = -1

swapIDTournamentList = {}

function useTournamentGraphicsInFriendly(id)
frTourn = id
end

function useGlobalTournamentGraphics(id)
gloTourn = id
end

function getTournamentGraphics(id)

if (gloTourn ~= -1) then
return gloTourn
end

if (id == -1) then
return frTourn
end

if (swapIDTournamentList[id] ~= nil) then
return swapIDTournamentList[id]
end

return id
end


function swapTournamentID(ida,idb)
swapIDTournamentList[ida] = idb
swapIDTournamentList[idb] = ida
end


teamTournament = {}

function assignTeamTournament(team,tourn)
teamTournament[team] = tourn
end


weatherAcc = {}
weatherAcc[0] = {}
weatherAcc[1] = {}
weatherAcc[2] = {}
weatherAcc[3] = {}
weatherAcc[0][0] = 0
weatherAcc[0][1] = 1
weatherAcc[1][0] = 1
weatherAcc[1][1] = 1
weatherAcc[2][0] = 1
weatherAcc[2][1] = 1
weatherAcc[3][0] = 0
weatherAcc[3][1] = 1


function setWinterAccessoriesWeather(weather,notwinter,winter)
weatherAcc[weather][0] = notwinter
weatherAcc[weather][1] = winter
end

function getWinterAccessoriesWeather(weather,winter)

if (weatherAcc[weather] ~= nil) then
if (weatherAcc[weather][winter] ~= nil) then
return (weatherAcc[weather][winter] == 1)
end
end

return true
end


winterAccessories = {}

function assignWinterAccessories(player,option)

if (type(option) == "number") then
winterAccessories[player] = option
else
winterAccessories[player] = option[math.random(#option)]
end

-- winterAccessories[player] = option
end

function getWinterAccessories(player,option)

if (winterAccessories[player] ~= nil) then
return winterAccessories[player]
end

if ((globalSleeveWinter[option] ~= nil) and (globalSleeveWinter[option] ~= -1)) then
return globalSleeveWinter[option]
end

return option
end


sleeveLength = {}

function setSleeveLength(player,option)

if (type(option) == "number") then
sleeveLength[player] = option
else
sleeveLength[player] = option[math.random(#option)]
end

-- sleeveLength[player] = option
end

function getSleeveLength(player,option)

if (sleeveLength[player] ~= nil) then
return sleeveLength[player]
end

if ((globalSleeve[option] ~= nil) and (globalSleeve[option] ~= -1)) then
return globalSleeve[option]
end

return option
end


globalSleeve = {}
globalSleeveWinter = {}


function setGlobalSleeveReplace(old,new)
globalSleeve[old] = new
end

function setGlobalWinterSleeveReplace(old,new)
globalSleeveWinter[old] = new
end

-- function setGlobalSleeveReplace(a,b,c,d,e)
-- globalSleeve[0] = a
-- globalSleeve[1] = b
-- globalSleeve[2] = c
-- globalSleeve[3] = d
-- globalSleeve[4] = e
-- end

-- function setGlobalWinterSleeveReplace(a,b,c,d,e)
-- globalSleeveWinter[0] = a
-- globalSleeveWinter[1] = b
-- globalSleeveWinter[2] = c
-- globalSleeveWinter[3] = d
-- globalSleeveWinter[4] = e
-- end



playersleevedry = {}
playersleevewet = {}
playersleevedrywin = {}
playersleevewetwin = {}
playersleevesnow = {}


function setSleeveAndUndershirtType(player,dry,wet,drywin,wetwin,snow)

-- playersleevedry[player] = dry
-- playersleevewet[player] = wet
-- playersleevedrywin[player] = drywin
-- playersleevewetwin[player] = wetwin
-- playersleevesnow[player] = snow


if (type(dry) == "number") then
playersleevedry[player] = dry
else
playersleevedry[player] = dry[math.random(#dry)]
end

if (type(wet) == "number") then
playersleevewet[player] = wet
else
playersleevewet[player] = wet[math.random(#wet)]
end

if (type(drywin) == "number") then
playersleevedrywin[player] = drywin
else
playersleevedrywin[player] = drywin[math.random(#drywin)]
end

if (type(wetwin) == "number") then
playersleevewetwin[player] = wetwin
else
playersleevewetwin[player] = wetwin[math.random(#wetwin)]
end

if (type(snow) == "number") then
playersleevesnow[player] = snow
else
playersleevesnow[player] = snow[math.random(#snow)]
end

end

function getSleeveAndUndershirtType(player,weather,climate,option)

if (weather == 2) then
if (playersleevesnow[player] ~= nil) then
return playersleevesnow[player]
end
end

if ((climate == 1) and (weather == 1)) then
if (playersleevewetwin[player] ~= nil) then
return playersleevewetwin[player]
end
end

if (climate == 1) then
if (playersleevedrywin[player] ~= nil) then
return playersleevedrywin[player]
end
end

if (weather == 1) then
if (playersleevewet[player] ~= nil) then
return playersleevewet[player]
end
end

if (playersleevedry[player] ~= nil) then
return playersleevedry[player]
end

return option
end



finalStad = {}
isFinal = false

function identifyTournamentFinalStadium(tourn,stad)
finalStad[tourn] = stad
end

function useTournamentFinalGraphics()
isFinal = true
end

function getTournamentFinal(tourn,stad,dist)

if (isFinal) then
return true
end

if (dist == 1) then
return true
end

if (finalStad[tourn] == stad) then
return true
end

return false
end


futCustom = false
 
function useCustomFUTAssets()
futCustom = true
end

function getSimpleColourCode(col)
	
	local b = col%256
	local g = (col-b)%65536 / 256
	local r = (col-(g*256)-b)%16777216 / 65536
	
	r = math.floor((r/85) + 0.5)
	g = math.floor((g/85) + 0.5)
	b = math.floor((b/85) + 0.5)
	
	return "1"..r..g..b
end


identifyVP = {-1,-1,-1,-1,-1,-1}


function importTeamStatements(home,away)
	teamTournament = {}
	
	gkKits = {}

	matchKit = {}

	swapKit = {}
	
	kitCollar = {}
	kitNumberSet = {}
	kitNumberColourShirt = {}
	kitNumberColourShort = {}
	kitNameFont = {}
	kitNameColour = {}
	kitFit = {}
	kitNameCurve = {}

	kitCollarTournament = {}
	kitNumberSetTournament = {}
	kitNumberColourShirtTournament = {}
	kitNumberColourShortTournament = {}
	kitNameFontTournament = {}
	kitNameColourTournament = {}
	kitFitTournament = {}
	kitNameCurveTournament = {}
	
	homeCrowdTeam = {}
	awayCrowdTeam = {}
	homeCrowdGame = {}
	awayCrowdGame = {}
	homeCrowdTournamentTeam = {}
	awayCrowdTournamentTeam = {}
	homeCrowdTournamentGame = {}
	awayCrowdTournamentGame = {}
	
	-- homeCrowdTournamentFinal = {}
	-- awayCrowdTournamentFinal = {}
	homeCrowdLeagueVersusLeague = {}
	awayCrowdLeagueVersusLeague = {}
	homeCrowdTournamentLeagueVersusLeague = {}
	awayCrowdTournamentLeagueVersusLeague = {}
	homeCrowdTeamVersusLeague = {}
	awayCrowdTeamVersusLeague = {}
	homeCrowdTournamentTeamVersusLeague = {}
	awayCrowdTournamentTeamVersusLeague = {}
	
	teamSeatsRemoved = {}
	
	
	gkPants = {}
	gkPantsTraining = {}
	gkPantsWinter = {}
	gkPantsSnow = {}

	jerseyTuck = {}

	sockHeight = {}

	kitFitPlayer = {}
	
	-- local vpMod = accessoryModel[30999]
	-- local vpCol = accessoryColour[30999]

	accessoryModel = {}
	accessoryColour = {}
	
	-- accessoryModel[30999] = vpMod
	-- accessoryColour[30999] = vpCol

	playerFace = {}

	winterAccessories = {}
	
	sleeveLength = {}
	
	undershortsPlayer = {}
	undershortsTeam = {}
	
	playerBoot = {}
	playerBootFallback = {}
	
	isGK = {}
	
	teamTracksuit = {}
	
	bannerInvert = {}
	
	genBootsPlayer = {}
	
	indivKitsTeam = {}
	
	altShorts = {}
	altSocks = {}
	altShortsSocks = {}
	
	
	swapKitTourn = {}

	teamKitColoursShirt1 = {}
	teamKitColoursShirt2 = {}
	teamKitColoursShort = {}
	teamKitColoursSock = {}

	teamKitColoursTournamentShirt1 = {}
	teamKitColoursTournamentShirt2 = {}
	teamKitColoursTournamentShort = {}
	teamKitColoursTournamentSock = {}
	
	
	customArmband = {}
	altKitFile = {}
	altKitFileTourn = {}
	altKitParts = {}
	altKitPartsOption = {}
	altKitPartsTourn = {}
	altKitPartsOptionTourn = {}
	gkKitOrder = {}
	gkKitOrderRand = {}
	gkKitOrderTourn = {}
	gkKitOrderRandTourn = {}
	playersleevedry = {}
	playersleevewet = {}
	playersleevedrywin = {}
	playersleevewetwin = {}
	playersleevesnow = {}
	bannerHomeOnly = {}
	matchKitTourn = {}
	
	genPlayerHairColour = {}
	overlayOffsetTeam = {}
	
	playergkglove = {}
	playerBootTeam = {}

	
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..home..".lua")
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..away..".lua")
	LoadAsyncWait()
end


--Revolution Mod 16 V1.3.5
--Edited by scouser09