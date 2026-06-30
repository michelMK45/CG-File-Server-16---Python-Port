frTourn = -1
gloTourn = -1

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

return id
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
winterAccessories[player] = option
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
sleeveLength[player] = option
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
	
	homeCrowdTournamentFinal = {}
	awayCrowdTournamentFinal = {}
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
	
	playerBoot = {}
	playerBootFallback = {}
	
	isGK = {}
	
	teamTracksuit = {}
	
	bannerInvert = {}
	
	genBootsPlayer = {}
	
	indivKitsTeam = {}

	
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..home..".lua")
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..away..".lua")
	LoadAsyncWait()
end


--Revolution Mod 16 V1.0
--Edited by scouser09