function PlayerUpdate(idx)
	local as = gSportsRNA
	local player = as:GetTable("wvPlayer", idx)
	local state = as:GetTable("wvState")

	db.player[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	db.player[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
	db.player[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	
	

	local weather = as:GetInt(state, "wvAttribStadWeather")
	local climate = as:GetInt(state, "wvAttribStadClimate") -- 0: warm, 1: cold

	if (weather == 1 or weather == 2) then
		db.player[idx].wet = 1
	else
		db.player[idx].wet = 0
	end

	if (weather == 1 or weather == 2 or climate == 1) then
		db.player[idx].cold = 1
	else
		db.player[idx].cold = 0
	end

	db.player[idx].stadiumType = as:GetInt(player, "stadiumType")

	db.player[idx].playerassetid = as:GetInt(player, "playerassetid")
	db.player[idx].teamid = as:GetInt(player, "teamid")
	db.player[idx].teamside = as:GetInt(player, "teamside")
	db.player[idx].isgoalie = as:GetInt(player, "goalie")
	
	-- female added in fifa 2016
	db.player[idx].gender = as:GetInt(player, "gender")  -- 0=male, 1=female
	db.player[idx].strgender = "male"
	
	if (db.player[idx].gender == 1) then
		db.player[idx].strgender = "female"
	end
	

	db.player[idx].kit = as:GetInt(player, "kit")
	db.player[idx].kitType = as:GetInt(player, "kitType") %20
	db.player[idx].kitYear = as:GetInt(player, "kitYear")

	local kitNumber = as:GetInt(player, "kitNumber")
	db.player[idx].kitNumberTens = math.floor ( kitNumber / 10 )
	db.player[idx].kitNumberUnits = math.floor ( math.fmod(kitNumber, 10) )

	db.player[idx].kitNameFont = as:GetInt(player, "kitNameFont")
	db.player[idx].kitNumberFont = as:GetInt(player, "kitNumberFont")
	db.player[idx].kitNumberColor = as:GetInt(player, "kitNumberColor")
	db.player[idx].kitNameColor = as:GetInt(player, "kitNameColor")

	db.player[idx].shortsNumberFont = as:GetInt(player, "shortsNumberFont")
	db.player[idx].shortsNumberColor = as:GetInt(player, "shortsNumberColor")
	db.player[idx].jerseyNameVisible = as:GetInt(player, "jerseyNameVisible")
	db.player[idx].jerseyNameLayout = as:GetInt(player, "jerseyNameLayout")

	db.player[idx].head = as:GetInt(player, "playerHead")
	db.player[idx].headClass = as:GetInt(player, "playerHeadClass")

	db.player[idx].jerseyCollarType = as:GetInt(player, "jerseyCollarType")
	db.player[idx].jerseySleeveLength = as:GetInt(player, "jerseySleeveLength")
	db.player[idx].jerseyArmBand = as:GetInt(player, "jerseyArmBand")
	db.player[idx].jerseyTucked = as:GetInt(player, "jerseyTucked")
	db.player[idx].jerseyfit = as:GetInt(player, "jerseyfit")
	db.player[idx].socklength = as:GetInt(player, "socklength")
	db.player[idx].shortstyle = as:GetInt(player, "shortstyle")

	db.player[idx].bodySkinToneType = as:GetInt(player, "playerBodySkinToneType")
	db.player[idx].headSkinToneType = as:GetInt(player, "playerHeadSkinToneType")
	db.player[idx].headSkinType = as:GetInt(player, "playerHeadSkinType")
	db.player[idx].playerBodySkinColor = as:GetInt(player, "playerBodySkinColor")
	db.player[idx].faceGenSkinToneType = as:GetInt(player, "faceGenSkinToneType")

	db.player[idx].shoeType = as:GetInt(player, "shoeType")
	db.player[idx].shoeDesign = as:GetInt(player, "shoeDesign")
	db.player[idx].shoeColorPri = as:GetInt(player, "shoeColorPrim")
	db.player[idx].shoeColorSec = as:GetInt(player, "shoeColorSec")
	db.player[idx].shoeColorTer = as:GetInt(player, "shoeColorTer")

	db.player[idx].faceType = as:GetInt(player, "faceType")
	db.player[idx].faceProxyHeadClass = as:GetInt(player, "faceProxyHeadClass")
	-- Faceproxyheadclass should never be greater than one including createplayer
	if (db.player[idx].faceProxyHeadClass == 2) then
		db.player[idx].faceProxyHeadClass = 1
	end

	db.player[idx].faceSideBurn = 0--as:GetInt(player, "faceSideBurn")
	db.player[idx].facialHairColor = as:GetInt(player, "facialHairColor")
	db.player[idx].facialHairType = as:GetInt(player, "facialHairType")
	db.player[idx].eyebrow = as:GetInt(player, "eyebrow")

	db.player[idx].isVirtualPro = as:GetInt(player, "isVirtualPro")
	db.player[idx].isCreatePlayer = as:GetInt(player, "isCreatePlayer")
	db.player[idx].faceTexExtension = "rx3"

	db.player[idx].isCreationZone = as:GetInt(player, "isFCZ")
	db.player[idx].hasCzCrestImage = as:GetInt(player, "hasCzCrestImage")
	db.player[idx].crestAssetId = as:GetInt(player, "crestAssetId")
	db.player[idx].forceunderarm = as:GetInt(player, "forceunderarm")
	db.player[idx].forceundershorts = as:GetInt(player, "forceundershorts")
	db.player[idx].forceunderneck = as:GetInt(player, "forceunderneck")

	db.player[idx].sponsorAssetId = as:GetInt(player, "sponsorAssetId")
	db.player[idx].hotspotJerseySponsorL = as:GetFloat(player, "hotspotJerseySponsorL")
	db.player[idx].hotspotJerseySponsorT = as:GetFloat(player, "hotspotJerseySponsorT")
	db.player[idx].hotspotJerseySponsorR = as:GetFloat(player, "hotspotJerseySponsorR")
	db.player[idx].hotspotJerseySponsorB = as:GetFloat(player, "hotspotJerseySponsorB")

	db.player[idx].kitColourJerseyPri = as:GetInt(player, "kitColourJerseyPri")
	db.player[idx].kitColourJerseySec = as:GetInt(player, "kitColourJerseySec")
	db.player[idx].kitColourJerseyTer = as:GetInt(player, "kitColourJerseyTer")

	db.player[idx].kitColourShortPri = as:GetInt(player, "kitColourShortPri")
	db.player[idx].kitColourShortSec = as:GetInt(player, "kitColourShortSec")
	db.player[idx].kitColourShortTer = as:GetInt(player, "kitColourShortTer")

	db.player[idx].kitColourSocksPri = as:GetInt(player, "kitColourSocksPri")
	db.player[idx].kitColourSocksSec = as:GetInt(player, "kitColourSocksSec")
	db.player[idx].kitColourSocksTer = as:GetInt(player, "kitColourSocksTer")

	db.player[idx].kitColourMaskPri = 0x00FF0000
	db.player[idx].kitColourMaskSec = 0x0000FF00
	db.player[idx].kitColourMaskTer = 0x000000FF

	db.player[idx].teamColorPri = 0x00FF0000
	db.player[idx].teamColorSec = 0x0000FF00
	db.player[idx].teamColorTer = 0x000000FF
	
	if (((db.player[idx].cold == 1) or trackSuitMode) and GetRMTracksuitType(idx)) then
		db.player[idx].teamColorPri = as:GetInt(player, "homeColourPri")
		db.player[idx].teamColorSec = as:GetInt(player, "homeColourSec")
		db.player[idx].teamColorTer = as:GetInt(player, "homeColourTer")
	end

	db.player[idx].sponsorcolour = as:GetInt(player, "sponsorcolour")

	db.player[idx].crestTexName = "crest_cm"

	if (db.player[idx].isCreationZone == 1 and db.player[idx].hasCzCrestImage > 0) then
		db.player[idx].crestTexName = "png";
	end

	db.player[idx].faceTexName = "head_"
	if (db.player[idx].isVirtualPro == 1) then
		db.player[idx].faceTexExtension = "dds"
		db.player[idx].faceTexName = "head.dds"
	end

	db.player[idx].faceTypeFallback = 0
	db.player[idx].headFallback = 0
	db.player[idx].faceSideBurnFallback = db.player[idx].faceSideBurn
	db.player[idx].facialHairColorFallback = db.player[idx].facialHairColor
	db.player[idx].facialHairTypeFallback = db.player[idx].facialHairType
	db.player[idx].headSkinTypeFallback = db.player[idx].headSkinType
	db.player[idx].headSkinToneTypeFallback = db.player[idx].headSkinToneType

	if(db.player[idx].headSkinToneTypeFallback == 1 or db.player[idx].headSkinToneTypeFallback == 3 or db.player[idx].headSkinToneTypeFallback == 7) then
		db.player[idx].headSkinToneTypeFallback = db.player[idx].headSkinToneTypeFallback + 1
	end

	-- If create player then we need the create player head
	-- head_{id}_{headClass}.rx2
	-- {id} == 0 is create player
	-- {id} == 1 is create player copy
	-- {id} == 2 is facegen head
	-- {id} == 3 is facegen head copy
 	if (db.player[idx].isCreatePlayer == 1) then
		db.player[idx].headClass = 2
		db.player[idx].faceProxyHeadClass = 1

		if (db.player[idx].isVirtualPro == 1) then
			db.player[idx].faceSideBurn = 0
			db.player[idx].facialHairColor = 0
			db.player[idx].facialHairType = 0
			db.player[idx].headSkinType = 0
			db.player[idx].headSkinToneType = 0
			db.player[idx].bodySkinToneType = 11 -- force body skin tone type to 11 (greyscale) for face gen

		end

	end


	db.player[idx].eyeColor = as:GetInt(player, "eyeColor")
	db.player[idx].hair = as:GetInt(player, "hair")
	db.player[idx].hairColor = as:GetInt(player, "hairColor")
	db.player[idx].compsuffix = ".rx3"

	
	
	--IF REFEREE
	if (db.player[idx].kitType == 5) then
	db.player[idx].playerassetid = db.player[idx].playerassetid + 500000
	db.player[idx].teamid = 6004
	end
	
	--IF VP
	if (db.player[idx].playerassetid == 30999) then
	identifyVP[1] = db.player[idx].shoeType
	identifyVP[2] = db.player[idx].hair
	identifyVP[3] = db.player[idx].hairColor
	identifyVP[4] = db.player[idx].eyeColor
	identifyVP[5] = db.player[idx].bodySkinToneType
	identifyVP[6] = kitNumber
	end
	
	
	-- local xb = tostring(db.player[idx].playerassetid)
	-- db.player[idx].kitNumberTens = tonumber(string.sub(xb,4,4))
	-- db.player[idx].kitNumberUnits = tonumber(string.sub(xb,5,5))
	-- if (string.len(xb) > (xidx-1)-1) then
	
	
	--if (db.player[idx].isCreatePlayer == 1) then
	if (db.player[idx].isVirtualPro == 1) then
	db.player[idx].playerassetid = 30999
	
	else
	if (db.player[idx].isCreatePlayer == 1) then
	
	
	if (db.player[idx].shoeType == identifyVP[1]) then
	if (db.player[idx].hair == identifyVP[2]) then
	if (db.player[idx].hairColor == identifyVP[3]) then
	if (db.player[idx].eyeColor == identifyVP[4]) then
	if (db.player[idx].bodySkinToneType == identifyVP[5]) then
	if ((kitNumber == identifyVP[6]) or (kitNumber == 1)) then
	-- if (db.player[idx].isCreatePlayer == identifyVP[7]) then
	-- if (db.player[idx].isCreatePlayer == identifyVP[8]) then
	-- if (db.player[idx].isCreatePlayer == identifyVP[9]) then
	-- if (db.player[idx].isCreatePlayer == identifyVP[10]) then
	
	db.player[idx].playerassetid = 30999
	
	end
	end
	end
	end
	end
	end
	



	
	
	
	end
	end
	
	
	local stadium = as:GetTable("wvStadium", 1)
		
	db.player[idx].homeKitTeamID = as:GetInt(stadium, "homeKitTeamID" )
	db.player[idx].awayKitTeamID = as:GetInt(stadium, "awayKitTeamID" )
	db.player[idx].homeKitTypeID = as:GetInt(stadium, "homeKitTypeID" )
	db.player[idx].awayKitTypeID = as:GetInt(stadium, "awayKitTypeID" )
	
	local outidx = 9
	if (db.player[idx].teamside == 1) then
	outidx = 20
	end
	
	local outplayer = as:GetTable("wvPlayer", outidx)
	
	local kitOutfield = as:GetInt(outplayer, "kit") 
	local kitTypeOutfield = as:GetInt(outplayer, "kitType") %20
	local kitYearOutfield = as:GetInt(outplayer, "kitYear")
	
	if (db.player[idx].kitYear > 0) then
	kitYearOutfield = db.player[idx].kitYear
	end
	
	db.player[idx].outfieldKitType = kitTypeOutfield
	
	--FUT FIX
	if (db.player[idx].teamid == 130000) then
	-- if ((futCustom) and ((futKits[db.player[idx].kitType] == db.player[idx].kit) or (futKits[db.player[idx].kitType] == nil))) then
	if ((futCustom) and ((futKits[kitTypeOutfield] == db.player[idx].kit) or (futKits[kitTypeOutfield] == nil))) then
	db.player[idx].kit = db.player[idx].teamid
	else
	db.player[idx].teamid = db.player[idx].kit
	end
	end
	
	
	-- local skyCategoryId = as:GetInt(state, "wvAttribSkyCategory")
	-- local skyAssetId = as:GetInt(state, "wvAttribSkyID")
	
	-- seed = (seed + (db.player[idx].playerassetid*idx) + (skyCategoryId*631) + (skyAssetId*983))%1000000
	
	--PLAYER FILES
	if (oldidx ~= idx) then
	if ((db.player[idx].isCreatePlayer ~= 1) or (db.player[idx].teamside ~= -1)) then
	if (db.player[idx].kit ~= db.player[idx].teamid) then
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..db.player[idx].kit..".lua")
	end
	LoadAsync("data/fifarna/lua/assignments/teams/team_"..db.player[idx].teamid..".lua")
	LoadAsync("data/fifarna/lua/assignments/players/player_"..db.player[idx].playerassetid..".lua")
	LoadAsync("data/fifarna/lua/assignments/playershoes/playershoe_"..db.player[idx].playerassetid..".lua")
	LoadAsyncWait()
	end

	
	if (idx == 0) then
	local temp = math.random(1,1000000)
	math.randomseed(seed + temp + 123456)
	math.random()
	math.random()
	math.random()
	end
	
	local randl = (idx + db.player[idx].playerassetid)%10
	for i=0,randl do
	math.random()
	end
	
	
	
	end
	oldidx = idx
	
	--FACE
	db.player[idx].headClass = getPlayerFace(db.player[idx].playerassetid,db.player[idx].headClass)
	db.player[idx].faceProxyHeadClass = getPlayerFace(db.player[idx].playerassetid,db.player[idx].faceProxyHeadClass)
	
	
	--Disable Player Faces
	if (disableRealPlayerFacesSwitch) then
	db.player[idx].headClass = 1
	db.player[idx].faceProxyHeadClass = 1
	db.player[idx].playerassetid = -1
	end
	
	

	if (db.player[idx].headClass == 0) then

		local playerassetid = db.player[idx].playerassetid

		db.player[idx].head = playerassetid
		-- db.player[idx].eyeColor = playerassetid

		db.player[idx].eyebrow = 0
		db.player[idx].faceType = playerassetid
		db.player[idx].faceSideBurn = 0
		db.player[idx].facialHairColor = 0
		db.player[idx].facialHairType = 0
		db.player[idx].headSkinType = 0
		db.player[idx].headSkinToneType = 0

		db.player[idx].hair = playerassetid
		db.player[idx].hairColor = 0
		db.player[idx].useFaceTextureComposition = 0
		db.player[idx].compsuffix = "_-1.rx3" -- avvoid loading layers for compositing if star head.
	else
		if(db.player[idx].headSkinToneType == 1 or db.player[idx].headSkinToneType == 3 or db.player[idx].headSkinToneType == 7) then
			db.player[idx].headSkinToneType = db.player[idx].headSkinToneType + 1
		end

		db.player[idx].useFaceTextureComposition = as:GetInt(player, "useFaceTextureComposition")
	
		if(db.player[idx].useFaceTextureComposition == 1) then
			db.player[idx].dxttype = "dxt1"
		elseif (db.player[idx].useFaceTextureComposition == 2) then
			db.player[idx].dxttype = "eadxt1"
		elseif (db.player[idx].useFaceTextureComposition == 3) then
			db.player[idx].dxttype = "rnadxt1"
		else
			db.player[idx].dxttype = "argb"
		end

		--tmp
		-- db.player[idx].hairColorIdx = db.player[idx].hairColor
		-- db.player[idx].hairColor = 0
	end
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	--RMCUSTOMSTART
	if (isPlayerGK(db.player[idx].playerassetid)) then
	db.player[idx].isgoalie = 1
	db.player[idx].kitType = 2
	end
	
	if ((db.player[idx].shoeType == 0) and repGenBoots) then
	if (not getPlayerGenericBoot(db.player[idx].playerassetid)) then
	db.player[idx].shoeType = getGenericBootReplacement(db.player[idx].playerassetid,db.player[idx].kitType)
	db.player[idx].shoeDesign = 0
	db.player[idx].shoeColorPri = hex("FF0000")
	db.player[idx].shoeColorSec = hex("00FF00")
	db.player[idx].shoeColorTer = hex("0000FF")
	end
	end
	
	
	
	
	-- local stadium = as:GetTable("wvStadium", 1)
		
	-- db.player[idx].homeKitTeamID = as:GetInt(stadium, "homeKitTeamID" )
	-- db.player[idx].awayKitTeamID = as:GetInt(stadium, "awayKitTeamID" )
	-- db.player[idx].homeKitTypeID = as:GetInt(stadium, "homeKitTypeID" )
	-- db.player[idx].awayKitTypeID = as:GetInt(stadium, "awayKitTypeID" )
	
	-- local outidx = 3
	-- if (db.player[idx].teamside == 1) then
	-- outidx = 14
	-- end
	
	-- local outplayer = as:GetTable("wvPlayer", outidx)
	
	-- local kitOutfield = as:GetInt(outplayer, "kit") 
	-- local kitTypeOutfield = as:GetInt(outplayer, "kitType") 
	-- local kitYearOutfield = as:GetInt(outplayer, "kitYear")
	
	-- db.player[idx].outfieldKitType = kitTypeOutfield
	
	local wipe3d = as:GetTable("wvWipe", 1)
	
	db.player[idx].tournid = as:GetInt(wipe3d, "leagueID")
	db.player[idx].tournid = getTournamentGraphics(db.player[idx].tournid)
	
	db.player[idx].classictournid = (kitYearOutfield*10000) + db.player[idx].tournid


	--IF GENERIC KIT
	db.player[idx].speckitType = -1
	if (db.player[idx].teamid == db.player[idx].kit) then
	db.player[idx].genkit = db.player[idx].teamid
	else
	db.player[idx].genkit = db.player[idx].kit
	if (db.player[idx].kitType ~= 5) then
	if ((db.player[idx].kit >= 5000) and (db.player[idx].kit < 8000)) then
	db.player[idx].kit = db.player[idx].teamid
	else
	db.player[idx].teamid = db.player[idx].kit
	end
	end
	end
	
	--PL REF KIT FIX
	if ((db.player[idx].kitType == 5) and (db.player[idx].kit > 6100)) then
	--db.player[idx].kit = db.player[idx].kit - 100
	db.player[idx].kit = 6000 + (db.player[idx].kit%10)
	end
	
	if ((db.player[idx].kitType == 5) and (db.player[idx].kit < 6004)) then
	db.player[idx].kit = 6004
	end
	
	--IF CLASSIC KIT
	if (db.player[idx].kitYear > 0) then
	db.player[idx].tournid = db.player[idx].kitYear
	end
	
	
	
	
	db.player[idx].defaulttournid = -1
	if (db.player[idx].kitType == 5) then
	if (kitYearOutfield > 0) then
	db.player[idx].tournid = kitYearOutfield
	end
	if (teamTournament[db.player[idx].homeKitTeamID] ~= nil) then
	db.player[idx].defaulttournid = getCloneTournamentRefereeKits(teamTournament[db.player[idx].homeKitTeamID])
	end
	else
	if (teamTournament[db.player[idx].teamid] ~= nil) then
	db.player[idx].defaulttournid = teamTournament[db.player[idx].teamid]
	end
	end
	
	--CLASSIC KIT BOOT DECADE
	db.player[idx].kitYearDecade = -1
	if (kitYearOutfield > 0) then
	db.player[idx].kitYearDecade = math.floor(kitYearOutfield/10)*10
	end
	
	--CLASSIC KIT ARMBAND
	if (kitYearOutfield > 0) then
	if (kitYearOutfield <= classicKitCaptainArmbandYear) then
	db.player[idx].jerseyArmBand = 0
	end
	end
	
	
	--CLASSIC GK KIT
	if ((db.player[idx].isgoalie == 1) and (kitYearOutfield > 0)) then
	db.player[idx].tournid = kitYearOutfield
	end
	
	--ARENA PLAYER KIT
	if ((idx < 8) and (db.player[idx].isgoalie == 0)) then
	db.player[idx].speckitType = 91
	end

	--ARENA GK KIT
	if ((idx < 8) and (db.player[idx].isgoalie == 1)) then
	db.player[idx].speckitType = 92
	end
	
	--TRAINING KIT HOME
	if ((db.player[idx].genkit == 7000) and (db.player[idx].kitType == 6)) then
	db.player[idx].speckitType = 93
	db.player[idx].kitType = 93
	db.player[idx].kitColourJerseyPri = 0x00FF0000
	db.player[idx].kitColourJerseySec = 0x0000FF00
	db.player[idx].kitColourJerseyTer = 0x000000FF
	db.player[idx].kitColourShortPri = 0x00FF0000
	db.player[idx].kitColourShortSec = 0x0000FF00
	db.player[idx].kitColourShortTer = 0x000000FF
	db.player[idx].kitColourSocksPri = 0x00FF0000
	db.player[idx].kitColourSocksSec = 0x0000FF00
	db.player[idx].kitColourSocksTer = 0x000000FF
	end
	
	--TRAINING KIT AWAY
	if ((db.player[idx].genkit == 7000) and (db.player[idx].kitType == 7)) then
	db.player[idx].speckitType = 94
	db.player[idx].kitType = 94
	db.player[idx].kitColourJerseyPri = 0x00FF0000
	db.player[idx].kitColourJerseySec = 0x0000FF00
	db.player[idx].kitColourJerseyTer = 0x000000FF
	db.player[idx].kitColourShortPri = 0x00FF0000
	db.player[idx].kitColourShortSec = 0x0000FF00
	db.player[idx].kitColourShortTer = 0x000000FF
	db.player[idx].kitColourSocksPri = 0x00FF0000
	db.player[idx].kitColourSocksSec = 0x0000FF00
	db.player[idx].kitColourSocksTer = 0x000000FF
	end
	
	if ((db.player[idx].isgoalie == 1) and (idx > 7)) then
	
	--TRAINING KIT HOME GK
	if ((kitOutfield == 7000) and (kitTypeOutfield == 6)) then
	db.player[idx].speckitType = 95
	end
	
	--TRAINING KIT HOME GK
	if ((kitOutfield == 7000) and (kitTypeOutfield == 7)) then
	db.player[idx].speckitType = 96
	end
	
	end
	
	--GK KITS
	if ((db.player[idx].isgoalie == 1) and (idx > 7)) then
	
	if (fixGenGK) then
	db.player[idx].kitNameFont = as:GetInt(outplayer, "kitNameFont")
	db.player[idx].kitNumberFont = as:GetInt(outplayer, "kitNumberFont")
	db.player[idx].shortsNumberFont = as:GetInt(outplayer, "shortsNumberFont")
	if ((db.player[idx].kitYearDecade > 0) and (classicGKMode)) then
	db.player[idx].kitNumberColor = 1
	db.player[idx].jerseyCollarType = 0
	db.player[idx].jerseyNameVisible = 0
	db.player[idx].kitNameColor = 0x00FFFFFF
	end
	-- db.player[idx].kitNameColor = hex("EEEEEE")
	end
	
	end
	
	--ALTERNATE GK
	-- if ((kitOutfield ~= 7000)) then
	-- db.player[idx].speckitType = kitTypeOutfield + 30
	-- end
	
	--
	-- if (db.player[idx].kitYear == 0) then
	-- if (db.player[idx].teamside == 0) then
	-- db.player[idx].speckitType = getGKKit(db.player[idx].kit,db.player[idx].homeKitTypeID,db.player[idx].homeKitTeamID,db.player[idx].awayKitTeamID,db.player[idx].kitType,db.player[idx].speckitType)
	-- else
	-- db.player[idx].speckitType = getGKKit(db.player[idx].kit,db.player[idx].awayKitTypeID,db.player[idx].homeKitTeamID,db.player[idx].awayKitTeamID,db.player[idx].kitType,db.player[idx].speckitType)
	-- end
	-- end
	
	-- end
	
	
	assignKitDetailsBackup(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNameFont,db.player[idx].kitNameColor,db.player[idx].jerseyNameLayout,db.player[idx].kitNumberFont,db.player[idx].shortsNumberFont,db.player[idx].kitNumberColor,db.player[idx].shortsNumberColor,db.player[idx].jerseyfit,db.player[idx].jerseyCollarType)
	

	-- --NON GK KIT
	-- if ((db.player[idx].isgoalie == 0) and (idx > 1)) then
	
	-- --SPECIFIC MATCH KIT
	-- if (db.player[idx].kitYear == 0) then
	-- db.player[idx].speckitType = getGameKit(db.player[idx].kit,db.player[idx].homeKitTeamID,db.player[idx].awayKitTeamID,db.player[idx].kitType,db.player[idx].speckitType)
	-- end
	
	-- end

	
	db.player[idx].tournidnum = getCloneTournamentNumbers(db.player[idx].tournid)
	db.player[idx].tournidkit = getCloneTournamentKits(db.player[idx].tournid,db.player[idx].teamid)
	db.player[idx].tournidref = getCloneTournamentRefereeKits(db.player[idx].tournid)
	db.player[idx].bibType = -1

	
	
	if (db.player[idx].kitYear == 0) then
	db.player[idx].kitType = getSwapKit(db.player[idx].kit,db.player[idx].kitType,db.player[idx].tournidkit)
	end
	
	
	--NEW KIT STUFF
	
	db.player[idx].speckitTypeShort = db.player[idx].speckitType
	db.player[idx].speckitTypeSock = db.player[idx].speckitType
	
	if (idx == 0) then
	homeoutfieldkittypechoice = -1
	awayoutfieldkittypechoice = -1
	homegkkittypechoice = -1
	awaygkkittypechoice = -1
	refereekittypechoice = -1
	homebibchoice = -1
	awaybibchoice = -1
	end
	
	
	local homeplayer = as:GetTable("wvPlayer", 9)
	local awayplayer = as:GetTable("wvPlayer", 20)
	local homegk = as:GetTable("wvPlayer", 8)
	local referee = as:GetTable("wvPlayer", 54)
	
	local matchhometeamid = as:GetInt(homeplayer, "teamid")
	local matchawayteamid = as:GetInt(awayplayer, "teamid")
	local matchhomegkteamid = as:GetInt(homegk, "teamid")
	
	local matchhomekitteam = as:GetInt(homeplayer, "kit") 
	local matchhomekittype = as:GetInt(homeplayer, "kitType") %20
	local matchhomekityear = as:GetInt(homeplayer, "kitYear")
	
	local matchawaykitteam = as:GetInt(awayplayer, "kit") 
	local matchawaykittype = as:GetInt(awayplayer, "kitType") %20
	local matchawaykityear = as:GetInt(awayplayer, "kitYear")
	
	local matchhomegkkitteam = as:GetInt(homegk, "kit") 
	local matchhomegkkittype = as:GetInt(homegk, "kitType") %20
	
	local refereekittype = as:GetInt(referee, "kit") 
	
	local temphomegk = -1
	local tempawaygk = -1
	
	local tournamentid = as:GetInt(wipe3d, "leagueID")
	tournamentid = getTournamentGraphics(tournamentid)
	tournamentid = getCloneTournamentKits(tournamentid,matchhometeamid)
	
	local matchhomekittourn = tournamentid
	local matchawaykittourn = tournamentid
	
	if (matchhomekityear > 0) then
	matchhomekittourn = matchhomekityear
	end
	
	if (matchawaykityear > 0) then
	matchawaykittourn = matchawaykityear
	end
	
	
	--FUT FIX
	if (matchhometeamid == 130000) then
	if ((futCustom) and ((futKits[matchhomekittype] == matchhomekitteam) or (futKits[matchhomekittype] == nil))) then
	matchhomekitteam = 130000
	end
	end
	
	if (matchawayteamid == 130000) then
	if ((futCustom) and ((futKits[matchawaykittype] == matchawaykitteam) or (futKits[matchawaykittype] == nil))) then
	matchawaykitteam = 130000
	end
	end
	
	if (matchhomekityear == 0) then
	matchhomekittype = getSwapKit(matchhomekitteam,matchhomekittype,matchhomekittourn)
	end
	if (matchawaykityear == 0) then
	matchawaykittype = getSwapKit(matchawaykitteam,matchawaykittype,matchawaykittourn)
	end
	
	
	if (idx > 7) then
	if (matchhomegkkittype == 2) then
	if (matchhomekitteam ~= 7000) then
	if (homeoutfieldkittypechoice == -1) then
	local newKitType = -1
	gamemodephase = 0
	
	--HOME KIT
	homeoutfieldkittypechoice = matchhomekittype
	if (matchhomekityear == 0) then
	homeoutfieldkittypechoice = getGameKit(matchhomekitteam,matchhomekitteam,matchawaykitteam,tournamentid,matchhomekittype,matchhomekittype)
	end
	newKitType = -1
	
	--AWAY KIT
	if (matchawaykityear == 0) then
	awayoutfieldkittypechoice = getGameKit(matchawaykitteam,matchhomekitteam,matchawaykitteam,tournamentid,matchawaykittype,-1)
	end
	if (awayoutfieldkittypechoice == -1) then
	newKitType = getAltKit(matchawaykitteam,matchhomekitteam,matchawaykittype,homeoutfieldkittypechoice,matchawaykittourn,matchhomekittourn,matchawaykityear,matchhomekityear)
	newKitType = getAltKitColour(matchawaykitteam,matchhomekitteam,newKitType,homeoutfieldkittypechoice,matchawaykittourn,matchhomekittourn,matchawaykityear,matchhomekityear,-1)
	if (newKitType ~= -1) then
	awayoutfieldkittypechoice = newKitType
	else
	awayoutfieldkittypechoice = matchawaykittype
	end
	end
	
	--end
	newKitType = -1
	
	--HOME GK KIT
	if (matchhomekityear == 0) then
	homegkkittypechoice = getGameKit(matchhomekitteam,matchhomekitteam,matchawaykitteam,tournamentid,2,-1)
	end
	if (homegkkittypechoice == -1) then
	newKitType = getGKKitColour(matchhomekitteam,matchawaykitteam,homeoutfieldkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,matchhomekittype,matchawaykittype,-1)
	if (newKitType ~= -1) then
	homegkkittypechoice = newKitType
	else
	homegkkittypechoice = 2
	temphomegk = matchhomekittype + 30
	end
	end
	
	newKitType = getAltKitColour(matchhomekitteam,matchawaykitteam,homegkkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,homeoutfieldkittypechoice)
	if (newKitType ~= -1) then
	homegkkittypechoice = newKitType
	temphomegk = -1
	end

	
	--end
	newKitType = -1
	
	--AWAY GK KIT
	if (matchawaykityear == 0) then
	awaygkkittypechoice = getGameKit(matchawaykitteam,matchhomekitteam,matchawaykitteam,tournamentid,2,-1)
	end
	if (awaygkkittypechoice == -1) then
	newKitType = getGKKitColour(matchawaykitteam,matchhomekitteam,awayoutfieldkittypechoice,homeoutfieldkittypechoice,matchawaykittourn,matchhomekittourn,matchawaykityear,matchhomekityear,matchawaykittype,matchhomekittype,homegkkittypechoice)
	if (newKitType ~= -1) then
	awaygkkittypechoice = newKitType
	else
	awaygkkittypechoice = 2
	tempawaygk = matchawaykittype + 30
	end
	end
	
	newKitType = getAltKitColour(matchawaykitteam,matchhomekitteam,awaygkkittypechoice,homeoutfieldkittypechoice,matchawaykittourn,matchhomekittourn,matchawaykityear,matchhomekityear,awayoutfieldkittypechoice)
	if (newKitType ~= -1) then
	awaygkkittypechoice = newKitType
	tempawaygk = -1
	end
	
	--end
	
	
	
	newKitType = -1
	
	--HOME GK KIT (SECOND PASS)
	homegkkittypechoice = -1
	if (matchhomekityear == 0) then
	homegkkittypechoice = getGameKit(matchhomekitteam,matchhomekitteam,matchawaykitteam,tournamentid,2,-1)
	end
	if (homegkkittypechoice == -1) then
	newKitType = getGKKitColour(matchhomekitteam,matchawaykitteam,homeoutfieldkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,matchhomekittype,matchawaykittype,awaygkkittypechoice)
	if (newKitType ~= -1) then
	homegkkittypechoice = newKitType
	else
	homegkkittypechoice = 2
	temphomegk = matchhomekittype + 30
	end
	end
	
	newKitType = getAltKitColour(matchhomekitteam,matchawaykitteam,homegkkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,homeoutfieldkittypechoice)
	if (newKitType ~= -1) then
	homegkkittypechoice = newKitType
	temphomegk = -1
	end

	
	--end
	
	
	
	
	
	
	if ((temphomegk ~= -1) and (matchhomekityear == 0)) then
	homegkkittypechoice = temphomegk
	end
	
	if ((tempawaygk ~= -1) and (matchawaykityear == 0)) then
	awaygkkittypechoice = tempawaygk
	end
	
	
	
	
	
	
	
	
	
	
	
	--REFEREE KIT
	newKitType = -1
	newKitType = getRefereeKitColour(matchhomekitteam,matchawaykitteam,homeoutfieldkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,refereekittype,db.player[idx].tournidref,homegkkittypechoice,awaygkkittypechoice)
	if (newKitType ~= -1) then
	refereekittypechoice = newKitType
	else
	refereekittypechoice = refereekittype
	end

	

	
	
	
	
	


	--HOME BIB
	homebibchoice = getBibColourType(matchhomekitteam,matchawaykitteam,homeoutfieldkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,db.player[idx].tournid,homegkkittypechoice,awaygkkittypechoice,refereekittypechoice,db.player[idx].tournidref,matchhomekitteam,-1)

	--AWAY BIB
	awaybibchoice = getBibColourType(matchawaykitteam,matchhomekitteam,awayoutfieldkittypechoice,homeoutfieldkittypechoice,matchawaykittourn,matchhomekittourn,matchawaykityear,matchhomekityear,db.player[idx].tournid,awaygkkittypechoice,homegkkittypechoice,refereekittypechoice,db.player[idx].tournidref,matchhomekitteam,homebibchoice)

	--HOME BIB (SECOND PASS)
	homebibchoice = getBibColourType(matchhomekitteam,matchawaykitteam,homeoutfieldkittypechoice,awayoutfieldkittypechoice,matchhomekittourn,matchawaykittourn,matchhomekityear,matchawaykityear,db.player[idx].tournid,homegkkittypechoice,awaygkkittypechoice,refereekittypechoice,db.player[idx].tournidref,matchhomekitteam,awaybibchoice)

	
	
	
	
	
	
	
	
	
	
	--end
	end
	
	
	
	
	
	
	
	
	
	


	
	
	if (db.player[idx].teamside == 0) then
	db.player[idx].bibType = homebibchoice
	if (db.player[idx].isgoalie == 0) then
	db.player[idx].speckitType = getIndividualKitPart(homeoutfieldkittypechoice,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(homeoutfieldkittypechoice,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(homeoutfieldkittypechoice,3)
	else
	db.player[idx].speckitType = getIndividualKitPart(homegkkittypechoice,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(homegkkittypechoice,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(homegkkittypechoice,3)
	end
	end
	
	if (db.player[idx].teamside == 1) then
	db.player[idx].bibType = awaybibchoice
	if (db.player[idx].isgoalie == 0) then
	db.player[idx].speckitType = getIndividualKitPart(awayoutfieldkittypechoice,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(awayoutfieldkittypechoice,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(awayoutfieldkittypechoice,3)
	else
	db.player[idx].speckitType = getIndividualKitPart(awaygkkittypechoice,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(awaygkkittypechoice,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(awaygkkittypechoice,3)
	end
	end	
	
	if (idx >= 54) then
	db.player[idx].kit = refereekittypechoice
	end
	
	
	
	
	end
	else
	
	--KIT SELECTION STUFF
	if (gamemodephase == 0) then
	kitCollarBackup = {}
	kitNumberSetShirtBackup = {}
	kitNumberSetShortsBackup = {}
	kitNumberColourShirtBackup = {}
	kitNumberColourShortBackup = {}
	kitNameFontBackup = {}
	kitNameColourBackup = {}
	kitFitBackup = {}
	kitNameCurveBackup = {}
	end
	gamemodephase = 1
	
	
	
	
	if (kitMenuClashing) then
	if (matchhomekitteam ~= 7000) then	
	
	--HOME TEAM KIT PREVIEW
	if (db.player[idx].teamside == 0) then
	
	-- local temphomekit = getSwapKit(matchhomegkkitteam,matchhomegkkittype,tournamentid) --getGameKit(matchhomegkkitteam,matchhomegkkitteam,db.player[idx].kit,matchhomegkkittype,matchhomegkkittype)
	
	db.player[idx].speckitType = getIndividualKitPart(db.player[idx].kitType,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(db.player[idx].kitType,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(db.player[idx].kitType,3)

	-- db.player[idx].speckitType = getIndividualKitPart(temphomekit,1)
	-- db.player[idx].speckitTypeShort = getIndividualKitPart(temphomekit,2)
	-- db.player[idx].speckitTypeSock = getIndividualKitPart(temphomekit,3)
	end

	
	--AWAY TEAM KIT PREVIEW
	if (db.player[idx].teamside == 1) then
	
	
	--HOME KIT
	if (matchhomegkteamid == 130000) then
	if ((futCustom) and ((futKits[0] == matchhomegkkitteam) or (futKits[0] == nil))) then
	matchhomegkkitteam = 130000
	end
	end
	
	local temphomekit = getSwapKit(matchhomegkkitteam,matchhomegkkittype,tournamentid) --getGameKit(matchhomegkkitteam,matchhomegkkitteam,db.player[idx].kit,matchhomegkkittype,matchhomegkkittype)
	
	
	
	
	--AWAY KIT
	local awaytourn = tournamentid
	if (db.player[idx].kitYear > 0) then
	awaytourn = db.player[idx].kitYear
	end
	
	
	local temptype = -1
	if (db.player[idx].kitYear == 0) then
	temptype = getGameKit(db.player[idx].kit,matchhomegkkitteam,db.player[idx].kit,tournamentid,db.player[idx].kitType,-1)
	end
	if (temptype == -1) then
	temptype = getAltKit(db.player[idx].kit,matchhomegkkitteam,db.player[idx].kitType,temphomekit,awaytourn,tournamentid,db.player[idx].kitYear,0)
	temptype = getAltKitColour(db.player[idx].kit,matchhomegkkitteam,temptype,temphomekit,awaytourn,tournamentid,db.player[idx].kitYear,0,-1)
	end
	db.player[idx].speckitType = getIndividualKitPart(temptype,1)
	db.player[idx].speckitTypeShort = getIndividualKitPart(temptype,2)
	db.player[idx].speckitTypeSock = getIndividualKitPart(temptype,3)
	end
	
	end
	end
	
	
	
	
	
	end
	end
	
	--END NEW KIT STUFF
	
	
	--db.player[idx].speckitType = db.player[idx].teamside + 1
	-- db.player[idx].speckitTypeShort = db.player[idx].speckitType + 1
	-- db.player[idx].speckitTypeSock = db.player[idx].speckitType + 2
	
	--gamemodephase = 0
	
	--assignKitDetailsBackup(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNameFont,db.player[idx].kitNameColor,db.player[idx].jerseyNameLayout,db.player[idx].kitNumberFont,db.player[idx].kitNumberColor,db.player[idx].shortsNumberColor,db.player[idx].jerseyfit,db.player[idx].jerseyCollarType)
	
	--,db.player[idx].classictournid
	
	--KIT DETAILS
	db.player[idx].kitNameFont = getKitNameFont(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNameFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].kitNumberFont = getKitNumberSet(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNumberFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid,1)
	db.player[idx].kitNumberColor = getKitNumberColourShirt(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNumberColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].kitNameColor = getKitNameColour(db.player[idx].kit,db.player[idx].kitType,db.player[idx].kitNameColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid,db.player[idx].kitNumberColor,db.player[idx].defaulttournid)
	db.player[idx].shortsNumberFont = getKitNumberSet(db.player[idx].kit,db.player[idx].kitType,db.player[idx].shortsNumberFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid,2)
	db.player[idx].shortsNumberColor = getKitNumberColourShort(db.player[idx].kit,db.player[idx].kitType,db.player[idx].shortsNumberColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyNameLayout = getKitNameCurve(db.player[idx].kit,db.player[idx].kitType,db.player[idx].jerseyNameLayout,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyCollarType = getKitCollar(db.player[idx].kit,db.player[idx].kitType,db.player[idx].jerseyCollarType,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyfit = getKitFit(db.player[idx].kit,db.player[idx].kitType,db.player[idx].jerseyfit,db.player[idx].tournidnum,db.player[idx].playerassetid,db.player[idx].kitYear,db.player[idx].classictournid)
	--KIT DETAILS ARENA/TRAINING/ALT GK
	if (db.player[idx].speckitType ~= -1) then
	db.player[idx].kitNameFont = getKitNameFont(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].kitNameFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].kitNumberFont = getKitNumberSet(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].kitNumberFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid,1)
	db.player[idx].kitNumberColor = getKitNumberColourShirt(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].kitNumberColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].kitNameColor = getKitNameColour(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].kitNameColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid,db.player[idx].kitNumberColor,db.player[idx].defaulttournid)
	db.player[idx].shortsNumberFont = getKitNumberSet(db.player[idx].kit,db.player[idx].speckitTypeShort,db.player[idx].shortsNumberFont,db.player[idx].tournidnum,db.player[idx].teamid,db.player[idx].kitYear,db.player[idx].classictournid,2)
	db.player[idx].shortsNumberColor = getKitNumberColourShort(db.player[idx].kit,db.player[idx].speckitTypeShort,db.player[idx].shortsNumberColor,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyNameLayout = getKitNameCurve(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].jerseyNameLayout,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyCollarType = getKitCollar(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].jerseyCollarType,db.player[idx].tournidnum,db.player[idx].kitYear,db.player[idx].classictournid)
	db.player[idx].jerseyfit = getKitFit(db.player[idx].kit,db.player[idx].speckitType,db.player[idx].jerseyfit,db.player[idx].tournidnum,db.player[idx].playerassetid,db.player[idx].kitYear,db.player[idx].classictournid)
	end
	
	--db.player[idx].kitNameFont = getKitNameVisible(db.player[idx].kit,db.player[idx].tournidnum,db.player[idx].kitNameFont)

	--REF KIT COLLAR
	if (db.player[idx].kitType == 5) then
	db.player[idx].jerseyCollarType = getTournamentRefereeKitsCollar(db.player[idx].tournidref,db.player[idx].jerseyCollarType,db.player[idx].defaulttournid)
	end
	
	--GK PANTS
	db.player[idx].shortstyle = getGKPants(db.player[idx].playerassetid,db.player[idx].shortstyle,db.player[idx].speckitType,weather,climate)
	
	--JERSEY TUCK
	db.player[idx].jerseyTucked = getJerseyTuck(db.player[idx].playerassetid,db.player[idx].jerseyTucked)
	
	--SOCK HEIGHT
	db.player[idx].socklength = getSockHeight(db.player[idx].playerassetid,db.player[idx].socklength)
	
	--ARMBAND
	db.player[idx].jerseyArmBandCustom = -1
	if (db.player[idx].jerseyArmBand == 1) then
	db.player[idx].jerseyArmBandCustom = getArmbandModel(db.player[idx].playerassetid,db.player[idx].jerseyArmBand)
	end
	
	
	

	--RANDOM BOOT
	db.player[idx].bootrand = math.random(0,3)
	db.player[idx].bootname = getPlayerShoe(db.player[idx].playerassetid,db.player[idx].teamid,"-1")
	
	if (type(db.player[idx].bootname) == "number") then
	db.player[idx].shoeType = db.player[idx].bootname
	db.player[idx].shoeDesign = 0
	end
	
	--RANDOM FACE
	db.player[idx].facerand = math.random(0,3)
	
	--CROWD FIX
	-- db.player[idx].crowd = ""
	-- if (idx < 2) then
	-- db.player[idx].crowd = "xxx"
	-- end
	
	
	db.player[idx].shortstyle = getTournamentShorts(db.player[idx].kit,db.player[idx].kitType,db.player[idx].tournid,db.player[idx].shortstyle)
	
	
	db.player[idx].shirtid = 1
	
	if (db.player[idx].teamside == 0) then
	if (idx < 19) then
	db.player[idx].shirtid = idx - 7
	else
	if (db.player[idx].isgoalie == 1) then
	db.player[idx].shirtid = 12
	else
	db.player[idx].shirtid = idx - 17
	end
	end
	end
	
	if (db.player[idx].teamside == 1) then
	if (idx < 30) then
	db.player[idx].shirtid = idx - 18
	else
	if (db.player[idx].isgoalie == 1) then
	db.player[idx].shirtid = 12
	else
	db.player[idx].shirtid = idx - 29
	end
	end
	end
	
	
	
	--TRACKSUIT MODE
	if (trackSuitMode) then
	db.player[idx].jerseyCollarType = -1
	db.player[idx].jerseySleeveLength  = -1
	db.player[idx].underneck = -1
	db.player[idx].underarms = -1
	db.player[idx].armLength = 1
	db.player[idx].shortstyle = -1
	db.player[idx].socklength = -1
	db.player[idx].cold = 1
	end
	
	if (bibMode) then
	db.player[idx].cold = 0
	end
	
	
	
	
	
	
	
	
	
	
	-- Seasonal Assets --
	-- These exist only here and not in the code:
	local seasonal = as:GetInt(player, "seasonaljersey")
	
	db.player[idx].useTextureComposition = as:GetInt(player, "useTextureComposition")
	
	--GET ACCESSORY WEATHER
	local winterAcc = getWinterAccessoriesWeather(weather,climate)
	db.player[idx].useWinterAcc = -1
	if (winterAcc) then
	db.player[idx].useWinterAcc = 1
	end
	
	--GET PLAYER WINTER ACCESSORIES
	if (db.player[idx].kitType == 5) then
	seasonal = getRefereeWinterAccessories(seasonal)
	end
	seasonal = getWinterAccessories(db.player[idx].playerassetid,seasonal)
	
	--SLEEVE LENGTH
	db.player[idx].jerseySleeveLength = getSleeveLength(db.player[idx].playerassetid,db.player[idx].jerseySleeveLength)

	if (db.player[idx].isVirtualPro == 1 or db.player[idx].isCreatePlayer == 1) then
	if ((seasonal < 0) or (seasonal > 4)) then
	seasonal = db.player[idx].jerseySleeveLength
	end
	end
	
	
		-- if ((getWinterAccessories(db.player[idx].playerassetid,seasonal) ~= nil) and winterAcc)
	
		-- if ((seasonal < 2) and not) then
			-- seasonal = db.player[idx].jerseySleeveLength
		-- end
	--elseif(db.player[idx].cold == 0) then
	--elseif (not winterAcc) then
	if (not winterAcc) then
		seasonal = db.player[idx].jerseySleeveLength
	end
	
	seasonal = getSleeveAndUndershirtType(db.player[idx].playerassetid,weather,climate,seasonal)
	
	if ((kitYearOutfield > 0) and (seasonal > 1)) then
	if (kitYearOutfield <= classicKitUndershirtYear) then
	if (seasonal == 2) then
	seasonal = 1
	else
	seasonal = 0
	end
	end
	end
	
	if (kitYearOutfield > 0) then
	if (db.player[idx].isgoalie == 1) then
	if (kitYearOutfield <= classicKitShortSleevesGKYear) then
	seasonal = 1
	end
	else
	if (kitYearOutfield <= classicKitShortSleevesOutfieldYear) then
	seasonal = 1
	end
	end
	end
	
	
	--FOURTH OFFICIAL
	db.player[idx].fourthofficialoption = getFourthOfficialKitType(weather,climate)
	
	if (db.player[idx].fourthofficialoption > 0) then
	if (idx == 57) then
	db.player[idx].jerseyCollarType = getFourthOfficialCollar(db.player[idx].tournid,db.player[idx].defaulttournid,0)
	seasonal = 1
	db.player[idx].jerseyTucked = 1
	if (db.player[idx].fourthofficialoption == 2) then
	db.player[idx].shortstyle = 1
	end
	end
	end
	
	
	

	if (seasonal == 0) then
		-- Short Sleeves
		db.player[idx].jerseySleeveLength  = 0
		db.player[idx].underneck = -1
		db.player[idx].underarms = -1
		db.player[idx].armLength = 0
	elseif (seasonal == 1) then
		-- Long Sleeves
		db.player[idx].jerseySleeveLength  = 1
		db.player[idx].underneck = -1
		db.player[idx].underarms = -1
		db.player[idx].armLength = 1
	elseif (seasonal == 2) then
		-- Long Sleeves and just underarmor neck
		db.player[idx].jerseySleeveLength = 1
		db.player[idx].underneck = 0
		db.player[idx].underarms = -1
		db.player[idx].armLength = 1
	elseif (seasonal == 3) then
		-- Short sleeves with underarmor arms no neck
		db.player[idx].jerseySleeveLength  = 0
		db.player[idx].underneck = -1
		db.player[idx].underarms = 0
		db.player[idx].armLength = 1
	elseif (seasonal == 4) then
		-- Short sleeves with underarmor neck and arms
		db.player[idx].jerseySleeveLength  = 0
		db.player[idx].underneck = 0
		db.player[idx].underarms = 0
		db.player[idx].armLength = 1
	end

	if (db.player[idx].cold > 0 or db.player[idx].isVirtualPro == 1 or db.player[idx].isCreatePlayer == 1) then
		db.player[idx].undershorts = 0
	else
		db.player[idx].undershorts = -1
	end
	
	--UNDERSHORTS
	db.player[idx].undershorts = getUndershorts(db.player[idx].playerassetid,db.player[idx].undershorts,kitYearOutfield,db.player[idx].kit)

	-- end of seasonal assets

	-- check if we need to force underwear for injuries
	if ( db.player[idx].forceunderarm == 1 ) then
		db.player[idx].jerseySleeveLength = 0
		db.player[idx].underarms = 0
		db.player[idx].armLength = 1
	end

	if ( db.player[idx].forceundershorts == 1 ) then
		db.player[idx].undershorts = 0
	end

	if ( db.player[idx].forceunderneck == 1 ) then
		db.player[idx].underneck = 0
	end

	-- Goalie long pants, turn off necessary assets.
	if( db.player[idx].shortstyle == 1 ) then
		db.player[idx].socklength = -1
		db.player[idx].undershorts = -1
	end

	db.player[idx].useTextureComposition = as:GetInt(player, "useTextureComposition")

	-- Females will not have tight jersey fit
	if (db.player[idx].gender == 1) then
		db.player[idx].jerseyfit = 0
		
	end
	
	
	if (((db.player[idx].isCreationZone == 0) and (db.player[idx].kitType ~= 5)) and (db.player[idx].speckitType < 91)) then
	--db.player[idx].sponsorAssetId = 1 --TEMP
	db.player[idx].sponsorcolour = 0xFFFFFFFF
	db.player[idx].hotspotJerseySponsorL = 0
	db.player[idx].hotspotJerseySponsorT = 0
	db.player[idx].hotspotJerseySponsorR = 1
	db.player[idx].hotspotJerseySponsorB = 1
	db.player[idx].useTextureComposition = 1
	end
	
	local crowd = as:GetTable("wvCrowd", 1)
	db.player[idx].crowdDistribution = as:GetInt(crowd, "crowdDistribution")
	
	

	
	
	db.player[idx].genTexString = db.player[idx].speckitType.."_"..db.player[idx].speckitTypeShort.."_"..db.player[idx].speckitTypeSock.."_"..db.player[idx].tournid.."_"..db.player[idx].crowdDistribution.."_"..db.player[idx].gender
	if (getIndividualKitsTeam(db.player[idx].kit,db.player[idx].kitType,db.player[idx].tournid,kitYearOutfield)) then
	db.player[idx].genTexString = db.player[idx].genTexString.."_"..db.player[idx].playerassetid.."_"..idx
	end
	
	--0-13
	--0,1,3,4,10
	-- db.player[idx].kit = as:GetInt(state, "wvAttribSkyID")
	-- db.player[idx].kitType = as:GetInt(state, "wvAttribSkyCategory")
	
	-- if (db.player[idx].kit == 0) then
	-- db.player[idx].kit = 21
	-- end
	-- if (db.player[idx].kit == 6) then
	-- db.player[idx].kit = 22
	-- end
	
	-- if (db.player[idx].kitType == 4) then
	-- db.player[idx].kitType = 2
	-- end
	
	-- db.player[idx].genkit = db.player[idx].kit
	
	
	-- db.player[idx].isfinal = getTournamentFinal(db.player[idx].tournid,db.player[idx].stadiumID,crowdDistribution)
	
	-- db.player[idx].kit = idx
	-- db.player[idx].kitType = 0
	
	--db.player[idx].cold = 0
	-- col1 = "000000"
	-- col2 = "FFFFFF"
	
-- r1 = tonumber(string.sub(col1,1,2),16)
-- g1 = tonumber(string.sub(col1,3,4),16)
-- b1 = tonumber(string.sub(col1,5,6),16)

-- r2 = tonumber(string.sub(col2,1,2),16)
-- g2 = tonumber(string.sub(col2,3,4),16)
-- b2 = tonumber(string.sub(col2,5,6),16)

-- val = math.sqrt(math.pow((r1-r2),2)+math.pow((g1-g2),2)+math.pow((b1-b2),2))


	
	--colx1 = getShirt1Colour(db.player[idx].kit,db.player[idx].kitType,db.player[idx].tournidkit,kitYearOutfield)

	-- homecolour1 = getShirt1Colour(db.player[idx].homeKitTeamID,db.player[idx].homeKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	-- awaycolour1 = getShirt1Colour(db.player[idx].awayKitTeamID,db.player[idx].awayKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	
	-- if (getColourDistance(homecolour1,awaycolour1) < 100) then
	-- db.player[idx].kitType = 2
	-- end
	
	-- homecolour1 = getShirt1Colour(db.player[idx].homeKitTeamID,db.player[idx].homeKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	-- homecolour2 = getShirt2Colour(db.player[idx].homeKitTeamID,db.player[idx].homeKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	-- awaycolour1 = getShirt1Colour(db.player[idx].awayKitTeamID,db.player[idx].awayKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	-- awaycolour2 = getShirt2Colour(db.player[idx].awayKitTeamID,db.player[idx].awayKitTypeID,db.player[idx].tournidkit,kitYearOutfield)
	
	
	
	
	-- if (idx == 8) then
	-- if (db.player[idx].kitType == 2) then
	--db.player[idx].speckitType = getGKKitColour(db.player[idx].homeKitTeamID,db.player[idx].awayKitTeamID,db.player[idx].homeKitTypeID,db.player[idx].awayKitTypeID,team1tourn,team2tourn,team1year,team2year)
	
	
	-- end
	-- end
	
	
	
	
	

	
	
	
	
	-- db.player[idx].kit = db.player[idx].kit%10
	-- db.player[idx].kitType = 0

	
-- if (idx == 54) then
	-- db.player[idx].kit = getRefereeKitColour(db.player[idx].homeKitTeamID,db.player[idx].awayKitTeamID,db.player[idx].homeKitTypeID,db.player[idx].awayKitTypeID,db.player[idx].tournidkit,db.player[idx].tournidkit,kitYearOutfield,kitYearOutfield,db.player[idx].kit,db.player[idx].tournid)
	-- end
	
	
	

	
	
	db.player[idx].overlayoffset = getKitOverlayVarient(db.player[idx].kit)

	
	
	--db.player[idx].speckitType = db.player[idx].bibType
	
	
	-- if (idx == 0) then
	-- homeid = 0
	-- awayid = 0
	-- --hometype = 0
    -- awaytype = 0
	-- end
	
	-- if (idx > 7) then
	-- if (homeid == 0) then
	-- homeid = math.random(14)
	-- hometype = hometype + 1
	-- end
	-- end
	
	-- db.player[idx].kit = homeid
	-- --db.player[idx].speckitType = 99999999
	-- db.player[idx].kitType = hometype
	
	
	
	
	-- if (db.player[idx].tournid < 0) then
	-- db.player[idx].kitNumberTens = -1
	-- db.player[idx].kitNumberUnits = -1
	-- else
	-- local xb = tostring(db.player[idx].tournid)
	-- if (idx > 7) then
	-- if (string.len(xb) > idx-8) then
	-- db.player[idx].kitNumberTens = -1
	-- db.player[idx].kitNumberUnits = tonumber(string.sub(xb,idx-7,idx-7))
	-- else
	-- db.player[idx].kitNumberTens = -1
	-- db.player[idx].kitNumberUnits = -1
	-- end
	-- end
	-- end
	
	
	
	
	
	--Force Players As Female
	if (forceFemale) then
	if (idx < 54) then
	if ((db.player[idx].kit < 112998) or (db.player[idx].kit > 113012)) then
	if ((db.player[idx].gender == 0) or ((db.player[idx].head < 5500) and (db.player[idx].headClass == 1))) then
	db.player[idx].gender = 1
	db.player[idx].strgender = "female"
	db.player[idx].jerseyfit = 0
	
	db.player[idx].head = getRandomFromID({5500,5501,5502,7000,7001,7002,7501},db.player[idx].playerassetid)
	db.player[idx].eyebrow = 4
	--db.player[idx].faceType = 5500
	db.player[idx].facialHairType = 0
	db.player[idx].headSkinType = 5
	db.player[idx].headSkinToneType = db.player[idx].bodySkinToneType

	db.player[idx].hair = getRandomFromID({501,505,510,512,536,539},db.player[idx].playerassetid)
	db.player[idx].headClass = 1
	db.player[idx].faceProxyHeadClass = 1
	db.player[idx].hairColor = as:GetInt(player, "hairColor")
	db.player[idx].facialHairColor = as:GetInt(player, "facialHairColor")
	db.player[idx].compsuffix = ".rx3"
	db.player[idx].dxttype = "dxt1"
	db.player[idx].useFaceTextureComposition = 1
	
	if(db.player[idx].headSkinToneType == 1 or db.player[idx].headSkinToneType == 3 or db.player[idx].headSkinToneType == 7) then
			db.player[idx].headSkinToneType = db.player[idx].headSkinToneType + 1
		end
	
	db.player[idx].playerassetid = -1
	end
	end
	end
	end
	
	

	
	
	
	
	--Female Hair Physics Fix
	db.player[idx].generichair = -1
	db.player[idx].genericfaceProxyHeadClass = -1
	if (db.player[idx].gender == 1) then
	db.player[idx].generichair = as:GetInt(player, "hair")
	db.player[idx].genericfaceProxyHeadClass = 1
	end
	
	--db.player[idx].jerseySleeveLength = 1
	

	
end

---------------------------------------------------------------------------------------------------
-- Get hair color for generic hair recoloring
function GetHairColorARGB(idx)
	hairColourList = { 0x00edac57, 0x000e0e0d, 0x00a07741, 0x001f160e,
                       0x00ffd286, 0x006e4d2b, 0x003b2816, 0x00782c08,
                       0x00c8c9cf, 0x00525355, 0x00345a34, 0x00263f67,
                       0x00f62f0a }

	local clr = 0x00FF0000
	if (db.player[idx].headClass > 0) then
		clr = hairColourList[db.player[idx].hairColor + 1]
		if (clr == nil) then
			clr = 0x00FF0000
		end
		clr = getGenericHairColour(db.player[idx].playerassetid,clr)
	else
		clr = 0x00808080
	end
	return clr
end

---------------------------------------------------------------------------------------------------
function GetSkinTexture(idx)
	
	local skintexture = "data/sceneassets/tattoo/tattoo_${db.player[?].playerassetid}_0.rx3;data/sceneassets/body/skin_${db.player[?].bodySkinToneType}_${db.player[?].gender}_textures.rx3"
	
	-- TODO: hardcoded for messi for now.
	-- if(db.player[idx].playerassetid == 158023) then
		-- return "data/sceneassets/tattoo/tattoo_${db.player[?].playerassetid}_${db.player[idx].headClass}.rx3;" .. skintexture
	-- end

	return skintexture
end

---------------------------------------------------------------------------------------------------
function EASWMorphFile(idx)
	if (db.player[idx].isVirtualPro == 1) then
		return string.format("data/easw/deltas.easwmorph") --12366)
	else
		return "dummyasset.easwmorph"
	end
end

---------------------------------------------------------------------------------------------------
function GetHeadAndHairAssetType(idx)
	if (db.player[idx].isCreatePlayer == 1) then
		return "cloneasset"
	else
		return ""
	end
end

---------------------------------------------------------------------------------------------------
function MorphFile(idx)
	if (db.player[idx].isCreatePlayer == 1 and db.player[idx].isVirtualPro == 0) then
		return "data/sceneassets/createplayer/head_0_2_0_1_morphtargets.rx3"
	else
		return "dummyasset.rx3"
	end
end

---------------------------------------------------------------------------------------------------
function PlayerAssetShadow(player, lod)
	local gr = gRenderables
	gr:AddAsset(player, lod, "shadow", "data/sceneassets/body/playershadow_5_1_0.rx3")
	gr:CreateMaterial(player, lod, "shadow", "missingShader.fx")
end

---------------------------------------------------------------------------------------------------
function GetCrestAsset(idx)
	if (db.player[idx].isCreationZone == 1) then
		if (db.player[idx].hasCzCrestImage > 0) then
			-- // The "\\" is so that the mounted image can be found properly by Apt
			return "data\\ugc/cz_crest/${db.player[?].crestAssetId}.png;data/ugc/cz_crest/1.png"
		else
			return "data/sceneassets/crest/crest_${db.player[?].crestAssetId}.rx3"
		end
	else
		return "${GetRMKit(?,0)}"
	end

end

---------------------------------------------------------------------------------------------------
function GetSkinTone(idx, lod)
	local useLight = false
	if (db.player[idx].isVirtualPro == 1) then
		-- // 0 is light, 1 is dark
		useLight = ( db.player[idx].faceGenSkinToneType == 0 )
	else
		useLight = ( db.player[idx].bodySkinToneType < 5 )
	end

	if ( useLight ) then
		return ( lod == 0 ) and "skin_light" or "skin_lod_light"
	else
		return ( lod == 0 ) and "skin_dark" or "skin_lod_dark"
	end
end

---------------------------------------------------------------------------------------------------
function GetFaceTone(idx, lod)
	local useLight = false
	if (db.player[idx].isVirtualPro == 1) then
		-- // 0 is light, 1 is dark
		useLight = ( db.player[idx].faceGenSkinToneType == 0 )
	else
		useLight = ( db.player[idx].bodySkinToneType < 5 )
	end

	if ( useLight ) then
		return ( lod == 0 ) and "face_light" or "face_lod_light"
	else
		return ( lod == 0 ) and "face_dark" or "face_lod_dark"
	end
end

-- these values match those in player.cpp
-- local VISIBILITY_GROUP_DEFAULT				= 1
-- local VISIBILITY_GROUP_JACKET				= "${GetRMTracksuitOption()}" -- visible on the bench, but not in game
-- local VISIBILITY_GROUP_JERSEY_ARMBAND		= "${GetRMBibOption(4)}"
-- local VISIBILITY_GROUP_JERSEY_NOARMBAND		= "${GetRMBibOption(8)}"
-- local VISIBILITY_GROUP_SHORTS				= "${GetRMBibOption(16)}"
-- local VISIBILITY_GROUP_HAIR					= 32
-- local VISIBILITY_GROUP_INGAME				= "${GetRMBibOption(64)}" -- for parts visible in game, but not on the bench
-- local VISIBILITY_GROUP_LEGS					= "${GetRMBibOption(128)}" -- socks, legs, and underwear, turn this stuff off when the player is wearing track pants, need a better name for this
local VISIBILITY_GROUP_DEFAULT				= 1
local VISIBILITY_GROUP_JACKET				= 2 -- visible on the bench, but not in game
local VISIBILITY_GROUP_JERSEY_ARMBAND		= 4
local VISIBILITY_GROUP_JERSEY_NOARMBAND		= 8
local VISIBILITY_GROUP_SHORTS				= 16
local VISIBILITY_GROUP_HAIR					= 32
local VISIBILITY_GROUP_INGAME				= 64 -- for parts visible in game, but not on the bench
local VISIBILITY_GROUP_LEGS					= 128 -- socks, legs, and underwear, turn this stuff off when the player is wearing track pants, need a better name for this
---------------------------------------------------------------------------------------------------
function PlayerAssetHighLod(player, lod)
	local gr = gRenderables

	local priority = 0	-- default priority


	-- rigamate assets
	gr:AddAsset(player, lod, "rigamatebody_rbo", "data/sceneassets/rigamate/player_rigamate_body_lod"..(lod).."_${db.player[?].strgender}.rbo")
	gr:AddAsset(player, lod, "rigamateface_rbo", "data/sceneassets/rigamate/player_rigamate_face_${db.player[?].strgender}.rbo")
	gr:AddAsset(player, lod, "rigamateface_rbt", "data/sceneassets/rigamate/fp_tuning_${db.player[?].head}_${db.player[?].headClass}.rbt;data/sceneassets/rigamate/fp_tuning_0_0.rbt")
	gr:AddAsset(player, lod, "rigamatejersey_wrinkle_rbo", "data/sceneassets/rigamate/player_rigamate_jersey_wrinkle_${db.player[?].strgender}.rbo")
	gr:AddAsset(player, lod, "rigamate_face_wrinkle_rbo", "data/sceneassets/rigamate/player_rigamate_face_wrinkle_${db.player[?].strgender}.rbo")

	-- GEO's
	gr:AddAsset(player, lod, "jersey_noarmband", "data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseyCollarType}_${db.player[?].jerseySleeveLength}_0_${db.player[?].jerseyTucked}_${db.player[?].jerseyfit}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAsset(player, lod, "jersey_armband", "${GetRMArmbandModel(?,"..(lod)..")}data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseyCollarType}_${db.player[?].jerseySleeveLength}_${db.player[?].jerseyArmBand}_${db.player[?].jerseyTucked}_${db.player[?].jerseyfit}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAsset(player, lod, "arms", "data/sceneassets/body/arms_"..(lod).."_${db.player[?].armLength}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "shorts", "${GetRMShortModel(?,"..(lod)..")}data/sceneassets/body/shorts_"..(lod).."_${db.player[?].shortstyle}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAsset(player, lod, "shoes",  "${GetRMBoot(?,0)}data/sceneassets/shoe/shoe_${db.player[?].shoeType}.rx3;data/sceneassets/shoe/shoe_15.rx3")
	gr:AddAsset(player, lod, "socks", "data/sceneassets/body/sock_"..(lod).."_${db.player[?].socklength}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "legs",  "data/sceneassets/body/legs_"..(lod).."_${db.player[?].socklength}_${db.player[?].gender}.rx3")
	gr:AddAssetEx(player, lod, "${GetHeadAndHairAssetType(?)}", "hair1", "${GetRMHairMod(?)}data/sceneassets/hair/hair_${db.player[?].hair}_${db.player[?].faceProxyHeadClass}_0.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAssetEx(player, lod, "${GetHeadAndHairAssetType(?)}", "hair2", "${GetRMHairMod(?)}data/sceneassets/hair/hair_${db.player[?].hair}_${db.player[?].faceProxyHeadClass}_0.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAssetEx(player, lod, "${GetHeadAndHairAssetType(?)}", "head",  "${GetRMFaceMod(?)}data/sceneassets/heads/head_${db.player[?].head}_${db.player[?].headClass}.rx3", priority, ASSET_MAKE_CPU_COPY)
    -- Point the eyes to the same asset the head uses, whether it being cloned or not.
	gr:AddAssetEx(player, lod, "fromasset", "eyes", "head")

	-- Add the morph files
	local temporary = 1	-- mark as temporary asset
	gr:AddAsset(player, lod, "morphhead", "${MorphFile(?)}", priority, ASSET_NO_COPY, temporary)
	gr:AddAsset(player, lod, "easwmorph", "${EASWMorphFile(?)}")
	
	skinTone = "${GetSkinTone(?,"..lod..")}"


	part = "arms"
	gr:CreateMaterialFromAttribulator(player, lod, part, "body_material",  skinTone)
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "skintex", "body_")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "normalMap", "bodycmn", "body_nm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "bodycmn", "body_coeff")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "bodydk", "body_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "bodydk", "body_region")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_brdf", "skinbrdf_texture")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_indirect_brdf", "skinindirectbrdf_texture")
	gr:SetConstantARGB(player, lod, part, "global", "skincolor", "${db.player[?].playerBodySkinColor}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")

	part = "legs"
	gr:CreateMaterialFromAttribulator(player, lod, part, "body_material", skinTone )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "skintex", "body_")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "normalMap", "bodycmn", "body_nm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "bodycmn", "body_coeff")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "bodydk", "body_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "bodydk", "body_region")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_brdf", "skinbrdf_texture")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_indirect_brdf", "skinindirectbrdf_texture")
	gr:SetConstantARGB(player, lod, part, "global", "skincolor", "${db.player[?].playerBodySkinColor}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_LEGS)

	-- hair1
	part = "hair1"
	gr:CreateMaterialFromAttribulator(player, lod, part, "hair_material", "${AttribMaterial('player_hair_kk_alphaA')}")
	gr:SetSubMesh(player, lod, part, "alphaA")
	gr:SetPriority(player, lod, part, 1)             -- haircap render before hair 2
	gr:SetSelfShadowAlpha(player, lod, part)          -- will use different self shadow shader that accounts for alpha
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "hairtex", "hair_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "hairtex", "hair_coeff")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetConstantARGB(player, lod, part, "global", "hairColor", "${GetHairColorARGB(?)}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")

	-- hair2
	part = "hair2"
	gr:CreateMaterialFromAttribulator(player, lod, part, "hair_material2", "${AttribMaterial('player_hair_kk_alphaB')}")
	gr:SetSubMesh(player, lod, part, "alphaB")
	gr:SetPriority(player, lod, part, 2)             -- strands render after hair 1
	gr:SetSelfShadowAlpha(player, lod, part)          -- will use different self shadow shader that accounts for alpha
	--gr:DisableSelfShadow(player, lod, part)          -- Don't render the hairstrands into the selfshadow.
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "hairtex", "hair_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "hairtex", "hair_coeff")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetConstantARGB(player, lod, part, "global", "hairColor", "${GetHairColorARGB(?)}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_HAIR)
	
end

---------------------------------------------------------------------------------------------------
function PlayerAssetLowLod(player, lod)
	local gr = gRenderables

	skinLodTone = "${GetSkinTone(?,"..lod..")}"

	local priority = 0	-- default priority

	-- rigamate lod assets
	gr:AddAsset(player, lod, "rigamatebody_rbo", "data/sceneassets/rigamate/player_rigamate_body_lod"..(lod).."_${db.player[?].strgender}.rbo")

	-- GEO's
	gr:AddAsset(player, lod, "shorts", "${GetRMShortModel(?,"..(lod)..")}data/sceneassets/body/shorts_"..(lod).."_${db.player[?].shortstyle}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
	gr:AddAsset(player, lod, "bodyskinlod", "data/sceneassets/body/body_"..(lod).."_${db.player[?].armLength}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "shoes", "${GetRMBoot(?,0)}data/sceneassets/body/shoes_"..(lod).."_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "socks", "data/sceneassets/body/sock_"..(lod).."_${db.player[?].socklength}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "head",  "data/sceneassets/body/head_"..(lod).."_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "eyes",  "data/sceneassets/body/head_"..(lod).."_${db.player[?].gender}.rx3")
	
	if (lod == 1) then
		gr:AddAsset(player, lod, "jersey_noarmband", "data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseyCollarType}_${db.player[?].jerseySleeveLength}_0_${db.player[?].jerseyTucked}_${db.player[?].jerseyfit}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
		gr:AddAsset(player, lod, "jersey_armband", "${GetRMArmbandModel(?,"..(lod)..")}data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseyCollarType}_${db.player[?].jerseySleeveLength}_${db.player[?].jerseyArmBand}_${db.player[?].jerseyTucked}_${db.player[?].jerseyfit}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
		
	elseif (lod == 2) then
		gr:AddAsset(player, lod, "jersey_noarmband", "data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseySleeveLength}_0_${db.player[?].jerseyTucked}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
		gr:AddAsset(player, lod, "jersey_armband", "${GetRMArmbandModel(?,"..(lod)..")}data/sceneassets/body/jersey_"..(lod).."_${db.player[?].jerseySleeveLength}_${db.player[?].jerseyArmBand}_${db.player[?].jerseyTucked}_${db.player[?].gender}.rx3", priority, ASSET_MAKE_CPU_COPY)
	end

	gr:AddAsset(player, lod, "hairlod",  "${GetRMHairModLod(?)}data/sceneassets/hairlod/hairlod_${db.player[?].hair}_${db.player[idx].faceProxyHeadClass}_0.rx3", priority, ASSET_MAKE_CPU_COPY)

	part = "bodyskinlod"
	gr:CreateMaterialFromAttribulator(player, lod, part, "body_material", skinLodTone )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "skintex", "body_")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "normalMap", "bodycmn", "body_nm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "bodycmn", "body_coeff")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "bodydk", "body_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "bodydk", "body_region")
	gr:SetConstantARGB(player, lod, part, "global", "skincolor", "${db.player[?].playerBodySkinColor}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")

	-- hair
	part = "hairlod"
	gr:CreateMaterialFromAttribulator(player, lod, part, "hair_material", "${AttribMaterial('player_hair_kk_alphaA_lod')}")
	gr:SetSubMesh(player, lod, part, "alphaA")
	gr:SetPriority(player, lod, part, 1)
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "hairtex", "hair_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "hairtex", "hair_coeff")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetConstantARGB(player, lod, part, "global", "hairColor", "${GetHairColorARGB(?)}")

end

---------------------------------------------------------------------------------------------------
function PlayerCommonBinding(player, lod)
	local gr = gRenderables

	local lodString = (lod == 0) and "" or "lod"

	faceTone = "${GetFaceTone(?,"..lod..")}"

	-- head
	part = "head"
	gr:CreateMaterialFromAttribulator(player, lod, part, "head_material", faceTone )
	gr:SetSubMesh(player, lod, part, "head")
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "facetex", "${db.player[?].faceTexName}")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "headcmn", "head_coeff")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")

    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_brdf", "skinbrdf_texture")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "skin_indirect_brdf", "skinindirectbrdf_texture")
    
	
	gr:SetTexture(player, lod, part, "textures", "specularScaleMap", "facespectex", "head_sk")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")

	gr:SetTexture(player, lod, part, "textures", "wrinkleMask", "headcmn", "head_mask_nm")

	-- Eyes
	part = "eyes"
	gr:CreateMaterialFromAttribulator(player, lod, part, "eye_material", "${AttribMaterial('eyes"..lodString.."')}" )
	gr:SetSubMesh(player, lod, part, "eyes")
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "eyetex", "eyes_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "headcmn", "eye_coeff")

	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "env_")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetTexture(player, lod, part, "textures", "normalMap", "headcmn", "eyes_nm")
    gr:SetTexture(player, lod, part, "textures", "eye_generic_ambient", "headcmn", "eyes_am")
    gr:SetTexture(player, lod, part, "textures", "eye_reflection", "headcmn", "eye_reflection")

	local part = "jersey_noarmband"
	gr:CreateMaterialFromAttribulator(player, lod, part, "jersey_material", "${AttribMaterial('jersey"..lodString.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "jersey_tex", "jersey_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "kittex_common", "jersey_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "jerseybnm", "jersey_nm")
	gr:SetTexture(player, lod, part, "textures", "jerseyPullMap", "jersey_pull_tex", "jersey_pull_mask")

	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "jerseydk", "jersey_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "jerseydk", "jersey_region")
	gr:SetTexture(player, lod, part, "textures", "numberTens", "kitnumbers", GetRMNumberStringTens())
	gr:SetTexture(player, lod, part, "textures", "numberUnits", "kitnumbers", GetRMNumberStringUnits())
	gr:SetTexture(player, lod, part, "textures", "tex_decalmap", "cresttex", "${db.player[?].crestTexName}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "jerseyName", "namestamp${?}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetHotSpot(player, lod, part, "global", "jersey_decalBounds", "kithotspots", "jersey", "team")
	gr:SetHotSpot(player, lod, part, "global", "jersey_nameBound", "kithotspots", "jersey", "name")
	gr:SetHotSpot(player, lod, part, "global", "jersey_nameArcCenter", "kithotspots", "jersey", "name_arccenter")
	gr:SetConstantInt(player, lod, part, "global", "jersey_nameLayout", "${db.player[?].jerseyNameLayout}")
	gr:SetConstantARGB(player, lod, part, "global", "jersey_nameColor", "${db.player[?].kitNameColor}")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_JERSEY_NOARMBAND)
	gr:SetTexture(player, lod, part, "textures", "twistMaskTexture", "jerseywrinklemask", "jersey_twist_mask")



	local part = "jersey_armband"
	gr:CreateMaterialFromAttribulator(player, lod, part, "jersey_material", "${AttribMaterial('jersey"..lodString.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "jersey_tex", "jersey_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "kittex_common", "jersey_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "jerseybnm", "jersey_nm")
	gr:SetTexture(player, lod, part, "textures", "jerseyPullMap", "jersey_pull_tex", "jersey_pull_mask")

	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "jerseydk", "jersey_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "jerseydk", "jersey_region")
	gr:SetTexture(player, lod, part, "textures", "numberTens", "kitnumbers", GetRMNumberStringTens())
	gr:SetTexture(player, lod, part, "textures", "numberUnits", "kitnumbers", GetRMNumberStringUnits())
	gr:SetTexture(player, lod, part, "textures", "tex_decalmap", "cresttex", "${db.player[?].crestTexName}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "jerseyName", "namestamp${?}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetHotSpot(player, lod, part, "global", "jersey_decalBounds", "kithotspots", "jersey", "team")
	gr:SetHotSpot(player, lod, part, "global", "jersey_nameBound", "kithotspots", "jersey", "name")
	gr:SetHotSpot(player, lod, part, "global", "jersey_nameArcCenter", "kithotspots", "jersey", "name_arccenter")
	gr:SetConstantInt(player, lod, part, "global", "jersey_nameLayout", "${db.player[?].jerseyNameLayout}")
	gr:SetConstantARGB(player, lod, part, "global", "jersey_nameColor", "${db.player[?].kitNameColor}")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_JERSEY_ARMBAND)
	gr:SetTexture(player, lod, part, "textures", "twistMaskTexture", "jerseywrinklemask", "jersey_twist_mask")


	part = "shorts"
	gr:CreateMaterialFromAttribulator(player, lod, part, "shorts_material", "${AttribMaterial('shorts"..lodString.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "shortstex", "shorts_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "shortstex", "shorts_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "shortsam_dry", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "shortsam_wet", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "shortsbnm", "shorts_nm")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "shortsdk", "shorts_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "shortsdk", "shorts_region")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "tex_decalmap", "cresttex", "${db.player[?].crestTexName}")
	gr:SetTexture(player, lod, part, "textures", "numberTens", "shortsnumbers", GetRMNumberStringTensShorts())
	gr:SetTexture(player, lod, part, "textures", "numberUnits", "shortsnumbers", GetRMNumberStringUnitsShorts())
	gr:SetHotSpot(player, lod, part, "global", "shorts_decalBounds", "shortshotspots", "shorts", "team")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_SHORTS)
	gr:SetTexture(player, lod, part, "textures", "twistMaskTexture", "shortswrinklemask", "shorts_twist_mask")


	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].kitColourShortPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].kitColourShortSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].kitColourShortTer}")

	part = "shoes"
	gr:CreateMaterialFromAttribulator(player, lod, part, "shoe_material", "${AttribMaterial('shoe"..lodString.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "shoetex", "shoe_cm")
	gr:SetTexture(player, lod, part, "textures", "normalMap", "shoetex", "shoe_nm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "shoetex", "shoe_coeff")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "shoesdk", "shoes_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "shoesdk", "shoe_region")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")

	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].shoeColorPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].shoeColorSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].shoeColorTer}")

	part = "socks"
	gr:CreateMaterialFromAttribulator(player, lod, part, "socks_material", "${AttribMaterial('sock"..lodString.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "shortstex2", "shorts_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "shortstex2", "shorts_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "shortsam_dry", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "shortsam_wet", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "shortsbnm", "shorts_nm")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "shortsdk", "shorts_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "shortsdk", "shorts_region")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_LEGS)

	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].kitColourSocksPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].kitColourSocksSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].kitColourSocksTer}")

	local jacketLodString = (lod == 0) and "" or "_lod"
	local part = "warmup_top"
	gr:CreateMaterialFromAttribulator(player, lod, part, "jacket_material", "jacket"..jacketLodString )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "warmuptextures", "top_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "warmuptextures", "top_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "warmuptextures", "top_nm")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].teamColorPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].teamColorSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].teamColorTer}")
	gr:SetVisibilityGroup(player, lod, part, GetRMTracksuitOption())

	local part = "warmup_bottom"
	gr:CreateMaterialFromAttribulator(player, lod, part, "jacket_material", "jacket"..jacketLodString )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "warmuptextures", "bottom_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "warmuptextures", "bottom_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "warmuptextures", "bottom_nm")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].teamColorPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].teamColorSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].teamColorTer}")
	gr:SetVisibilityGroup(player, lod, part, GetRMTracksuitOption())


	local undergearMat = (lod == 0) and "undergear" or "socklod"

	--underarmor neck
	local part = "underneck"
	gr:CreateMaterialFromAttribulator(player, lod, part, "underneck_material", "${AttribMaterial('"..undergearMat.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "jersey_tex", "jersey_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "kittex_common", "jersey_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "jerseybnm", "jersey_nm")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "jerseydk", "jersey_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "jerseydk", "jersey_region")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_LEGS)

	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].kitColourMaskPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].kitColourMaskSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].kitColourMaskTer}")

	--underarmor sleeves
	local part = "underarms"
	gr:CreateMaterialFromAttribulator(player, lod, part, "underarms_material", "${AttribMaterial('"..undergearMat.."')}" )
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "jersey_tex", "jersey_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "kittex_common", "jersey_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "jerseyam_dry", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "jerseyam_wet", "jersey_am")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "jerseybnm", "jersey_nm")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "jerseydk", "jersey_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "jerseydk", "jersey_region")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_LEGS) -- as the legs are turned off underneath the track suit

	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].kitColourMaskPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].kitColourMaskSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].kitColourMaskTer}")

	--undershorts
	local part = "undershorts"
	gr:CreateMaterialFromAttribulator(player, lod, part, "undershorts_material", "${AttribMaterial('"..undergearMat.."')}")
	gr:SetTexture(player, lod, part, "textures", "diffuseTexture", "shortstex", "shorts_cm")
	gr:SetTexture(player, lod, part, "textures", "coeffMap", "shortstex", "shorts_coeff")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_dry", "shortsam_dry", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "occlusionMap_wet", "shortsam_wet", "shorts_am")
	gr:SetTexture(player, lod, part, "textures", "wrinkleMap", "shortsbnm", "shorts_nm")
	gr:SetTexture(player, lod, part, "textures", "dirtMapArray", "shortsdk", "shorts_dk")
	gr:SetTexture(player, lod, part, "textures", "dirtMaskTexture", "shortsdk", "shorts_region")
	gr:SetTexture(player, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(player, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTexture(player, lod, part, "textures", "weavePatternNormalMap", "cmnweave", "kit_weave_nm")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "coverageMap", "covmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
    gr:SetTextureFromRuntime(player, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.player[?].stadiumID}_${db.player[?].stadiumLightID}_${db.player[?].stadiumType}")
	gr:SetTextureFromRuntime(player, lod, part, "textures", "ssao_texture", "ssao")
	gr:SetVisibilityGroup(player, lod, part, VISIBILITY_GROUP_LEGS)

	gr:SetConstantARGB(player, lod, part, "global", "customColorPri", "${db.player[?].kitColourShortPri}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorSec", "${db.player[?].kitColourShortSec}")
	gr:SetConstantARGB(player, lod, part, "global", "customColorTer", "${db.player[?].kitColourShortTer}")

end

---------------------------------------------------------------------------------------------------
function GetFaceTextureOperation(idx)
	if(db.player[idx].isVirtualPro == 1) then
		return "extracttexture head.dds"
	elseif (db.player[idx].useFaceTextureComposition > 0) then
		-- assetOperation generatetexture: "generatetexture texname width, height, mipCount, compression"
		--return "generatetexture head_ 512,1024,6,${db.player[?].dxttype}"
		return "generatetexture head_ 1024,1024,6,${db.player[?].dxttype}"
	else
		-- For others we do not need to generate the texture, so we just extract the source asset
		return "extracttexture head_"
	end
end

---------------------------------------------------------------------------------------------------
function GetFaceSpecTextureOperation(idx)
	if(db.player[idx].isVirtualPro == 1) then
		-- gameface, no information about facial hair type
		return "extracttexture head_sk"
	elseif (db.player[idx].useFaceTextureComposition > 0) then
		-- assetOperation generatetexture: "generatetexture texname width, height, mipCount, compression"
		return "generatetexture head_sk 512,512,6,${db.player[?].dxttype}"
	else
		-- For others we do not need to generate the texture, so we just extract the source asset
		return "extracttexture head_sk"
	end
end

---------------------------------------------------------------------------------------------------
function GetFaceTexTemplate(idx)
	if(db.player[idx].isVirtualPro == 1) then
		return "data/easw/head.dds;data/sceneassets/gameface/head.dds"
	elseif(db.player[idx].useFaceTextureComposition > 0) then
		return "gentex_face_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures."..db.player[idx].faceTexExtension
	else
		return "${GetRMFaceTex(?)}data/sceneassets/faces/face_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures."..db.player[idx].faceTexExtension
	end
end

---------------------------------------------------------------------------------------------------
function GetFaceSpecAoTexTemplate(idx)
	if(db.player[idx].isVirtualPro == 1) then
		return "data/sceneassets/heads/head_common_${db.player[?].gender}_textures.rx3"
	elseif(db.player[idx].headClass > 0) then
		return "gentex_facespec_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures."..db.player[idx].faceTexExtension
	else
		return "${GetRMFaceTex(?)}data/sceneassets/faces/face_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures."..db.player[idx].faceTexExtension
	end
end

---------------------------------------------------------------------------------------------------
function GetFaceNormalTexTemplate(idx)
	if(db.player[idx].headClass == 0) then
		return "${GetRMFaceTex(?)}data/sceneassets/faces/face_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures."..db.player[idx].faceTexExtension
	else
		return "data/sceneassets/heads/head_common_${db.player[?].gender}_textures.rx3"
	end
end

---------------------------------------------------------------------------------------------------
function GetJerseyBMN(idx)
	return "data/sceneassets/kitcmn/jersey_${db.player[?].jerseyTucked}_${db.player[?].jerseyfit}_${db.player[?].gender}_bnm.rx3"
end

---------------------------------------------------------------------------------------------------
function GetShortsBMN(idx)
	return "data/sceneassets/kitcmn/shorts_${db.player[idx].shortstyle}_${db.player[?].gender}_bnm.rx3"
end

---------------------------------------------------------------------------------------------------
-- returns kit texture or goalie pants kit 5200
function GetShortsTex(idx,pos)
	if (db.player[idx].fourthofficialoption == 2) then
	if (idx == 57) then
	return "${GetRMKit(?,"..pos..")}"
	end
	end
	if(db.player[idx].shortstyle == 1) then
		return "data/sceneassets/kit/kit_${db.player[?].kit}_99_0.rx3;data/sceneassets/kit/kit_5200_0_0.rx3"
	else
		return "${GetRMKit(?,"..pos..")}"
	end
end

function GetKitTextureOperation(idx)
	if (db.player[idx].useTextureComposition == 1) then
		-- Creation Zone requires generated textures, describe the operation
		-- assetOperation generatetexture: "generatetexture texname width, height, mipCount, compression"
		--return "generatetexture jersey_cm 1024,1024,9,eadxt1"
		return "generatetexture jersey_cm "..gentexsize..","..gentexsize..","..gentexmip..","..gentexformat
	else
		-- For others we do not need to generate the texture, so we just extract the source asset
		return "extracttexture jersey_cm"
	end
end

function GetKitTextureAssetName(idx)
	if (db.player[idx].useTextureComposition == 1) then
		-- Creation Zone requires generated textures, thus give the asset a unique name
		-- For CZ, kittype is always home, and year is always zero.
		--return "gentex_kit_${db.player[?].kit}_${db.player[?].kitType}_${db.player[?].kitYear}_${db.player[?].teamside}_${db.player[?].kitColourJerseyPri}_${db.player[?].kitColourJerseySec}_${db.player[?].kitColourJerseyTer}_${db.player[?].playerassetid}"
		return "gentex_kit_${db.player[?].kit}_${db.player[?].kitType}_${db.player[?].kitYear}_${db.player[?].teamside}_${db.player[?].kitColourJerseyPri}_${db.player[?].kitColourJerseySec}_${db.player[?].kitColourJerseyTer}_${db.player[?].genTexString}"
	else
		-- Keep regular rx3 name as this is the source of the texture
		return "${GetRMKit(?,1)}"
	end
end

---------------------------------------------------------------------------------------------------
function GetSimpleClothJersey(idx)
	if(db.player[idx].jerseyfit == 0) then
		return "data/sceneassets/simplecloth/simjersey_0_0_${db.player[?].jerseySleeveLength}_${db.player[?].jerseyArmBand}_${db.player[?].jerseyTucked}_${db.player[?].gender}.rx3"
		--return "data/sceneassets/simplecloth/simjersey_0_0_0_0_1.rx3"
	else
		return "data/sceneassets/simplecloth/dummy_-1.rx3"
	end
end

function GetSimpleClothShorts(idx)
	if(db.player[idx].shortstyle == 0) then
		return "data/sceneassets/simplecloth/simshorts_0_${db.player[?].shortstyle}_${db.player[?].gender}.rx3"
		--return "data/sceneassets/simplecloth/simshorts_0_0.rx3"
	else
		return "data/sceneassets/simplecloth/dummy_-1.rx3"
	end
end

---------------------------------------------------------------------------------------------------
function PlayerAssetLod(player, lod)
	local gr = gRenderables

	local defaultpriority = 0	-- default priority

	gr:AddCallback(player, lod, "PlayerUpdate(?)")

	local kitTexAsset = "${GetRMKit(?,1)}"
	local kitTexAssetPos = "${GetRMKit(?,1)}"

	-- Generic files needed by all LODs
	gr:AddAsset(player, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(player, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.player[?].envLighting}.rx3")
	gr:AddAsset(player, lod, "bodycmn", "data/sceneassets/body/body_common_${db.player[?].gender}_textures.rx3")
	gr:AddAsset(player, lod, "headcmn", "${GetRMFaceBump(?)}data/sceneassets/heads/head_common_${db.player[?].gender}_textures.rx3")
        
    local faceNRMTemplate = "${GetFaceNormalTexTemplate(?)}"
	gr:AddAsset(player, lod, "facenormaltex", faceNRMTemplate)
    gr:AddAsset(player, lod, "facenormaltex_common", "${GetRMFaceBump(?)}data/sceneassets/heads/head_common_${db.player[?].gender}_textures.rx3")
    
	-- Sponsor image for stamping onto kit
	gr:AddAsset(player, lod, "sponsortex", "${GetRMKitOverlay(?)}data/ugc/cz_sponsor/${db.player[?].sponsorAssetId}.png;data/ugc/cz_sponsor/1.png", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)

	-- gr:AddAssetEx(asset, lod, assetOperation, assetPart, containerName)
	-- extracttexture will create an asset with just the texture you extract from the source asset, this way we can free the original rx3, freeing unused textures.
	gr:AddAssetEx(player, lod, "extracttexture jersey_coeff", "kittex_common" , kitTexAsset)
	gr:AddAssetEx(player, lod, "extracttexture shorts_cm,shorts_coeff", "shortstex" , "${GetShortsTex(?,2)}")
	gr:AddAssetEx(player, lod, "extracttexture shorts_cm,shorts_coeff", "shortstex2" , "${GetShortsTex(?,3)}")
	gr:AddAssetEx(player, lod, "extracthotspots", "kithotspots" , kitTexAssetPos)
	gr:AddAssetEx(player, lod, "extracthotspots", "shortshotspots",  "${GetShortsTex(?,2)}")
	gr:AddAssetEx(player, lod, "extracttexture ${db.player[?].crestTexName}", "cresttex", "${GetCrestAsset(?)}")


	-- Texture composition code
	-- Add the template asset as a temporary asset, auto releasing it when it's not being used (after texture generation in this case)
	gr:AddAssetEx(player, lod, "extracttexture jersey_cm", "kittex_cm_template" , kitTexAsset, defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)
	local part = "jersey_tex"
	-- GetKitTextureOperation will determine if texture composition is needed.
	gr:AddAssetEx(player, lod, "${GetKitTextureOperation(?)}", part , "${GetKitTextureAssetName(?)}")
	-- Describe texture composition in case we have to generate the texture, this material won't be created if no composition is needed.
	gr:CreateMaterial(player, lod, part, "texcomp.fx" )
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex0", "kittex_cm_template", "jersey_cm")
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex1", "sponsortex", "png")
	gr:SetConstantARGB(player, lod, part, "global", "recolorCustomColorPri", "${db.player[?].kitColourJerseyPri}")
	gr:SetConstantARGB(player, lod, part, "global", "recolorCustomColorSec", "${db.player[?].kitColourJerseySec}")
	gr:SetConstantARGB(player, lod, part, "global", "recolorCustomColorTer", "${db.player[?].kitColourJerseyTer}")
	gr:SetConstantARGB(player, lod, part, "global", "recolourMult", "${db.player[?].sponsorcolour}")
	gr:SetConstantHotSpot(player, lod, part, "global", "samplerBounds1", "${db.player[?].hotspotJerseySponsorL};${db.player[?].hotspotJerseySponsorT};${db.player[?].hotspotJerseySponsorR};${db.player[?].hotspotJerseySponsorB}")
	-- End of texture composition

	-- Set the jersey texture as a runtime texture so we can use it outside of player
	gr:SetRuntimeTexture(player, lod, "jersey_${db.player[?].kit}_${db.player[?].kitType}_${db.player[?].isgoalie}_${db.player[?].teamside}" , "jersey_tex", "jersey_cm")
	gr:SetRuntimeTexture(player, lod, "jersey_coeff_${db.player[?].kit}_${db.player[?].kitType}_${db.player[?].isgoalie}_${db.player[?].teamside}", "kittex_common",  "jersey_coeff")

	gr:AddAsset(player, lod, "shoetex", "${GetRMBoot(?,1)}data/sceneassets/shoe/shoe_${db.player[?].shoeType}_${db.player[?].shoeDesign}_textures.rx3;data/sceneassets/shoe/shoe_15_0_textures.rx3")
	gr:AddAsset(player, lod, "skintex", "${GetRMSkin(?)}${GetSkinTexture(?)}")

	gr:AddAsset(player, lod, "hairtex", "${GetRMHairTex(?)}data/sceneassets/hair/hair_${db.player[?].hair}_${db.player[?].faceProxyHeadClass}_textures.rx3")
	gr:AddAsset(player, lod, "shortsam_dry", "data/sceneassets/kitcmn/shorts_${db.player[?].shortstyle}_0_${db.player[?].gender}_textures.rx3")
	gr:AddAsset(player, lod, "shortsam_wet", "data/sceneassets/kitcmn/shorts_${db.player[?].shortstyle}_1_${db.player[?].gender}_textures.rx3")
	gr:AddAsset(player, lod, "jerseyam_dry", "data/sceneassets/kitcmn/jersey_${db.player[?].jerseyTucked}_0_${db.player[?].gender}_textures.rx3")
	gr:AddAsset(player, lod, "jerseyam_wet", "data/sceneassets/kitcmn/jersey_${db.player[?].jerseyTucked}_1_${db.player[?].gender}_textures.rx3")
	local jerseyBNM = "${GetJerseyBMN(?)}"
	gr:AddAsset(player, lod, "jerseybnm", jerseyBNM)
	gr:AddAsset(player, lod, "jersey_pull_tex", "data/sceneassets/kitcmn/jersey_${db.player[?].gender}_pull_mask.rx3")

	gr:AddAsset(player, lod, "cmnweave", "data/sceneassets/kitcmn/kitweave.rx3")
	local shortsBNM = "${GetShortsBMN(?)}"
	gr:AddAsset(player, lod, "shortsbnm", shortsBNM)

	-- Dirt masks
	gr:AddAsset(player, lod, "bodydk", "data/sceneassets/body/body_dk.rx3")
	gr:AddAsset(player, lod, "shortsdk", "data/sceneassets/kitcmn/shorts_${db.player[?].shortstyle}_${db.player[?].gender}_dk.rx3")
	gr:AddAsset(player, lod, "jerseydk", "data/sceneassets/kitcmn/jersey_${db.player[?].gender}_dk.rx3")
	gr:AddAsset(player, lod, "shoesdk", "data/sceneassets/shoe/shoes_dk.rx3")
	
	gr:AddAsset(player, lod, "jerseywrinklemask", "data/sceneassets/kitcmn/jersey_${db.player[?].gender}_twist_mask.rx3");
	gr:AddAsset(player, lod, "shortswrinklemask", "data/sceneassets/kitcmn/shorts_${db.player[?].gender}_twist_mask.rx3");

	-- gr:AddAsset(player, lod, "eyetex", "data/sceneassets/heads/eyes_${db.player[?].eyeColor}_${db.player[?].faceProxyHeadClass}_textures.rx3")
	gr:AddAsset(player, lod, "eyetex", "${GetRMEyeTex(?)}data/sceneassets/heads/eyes_${db.player[?].eyeColor}_1_textures.rx3")

	-- Add font as a temporary asset, because the font is used after the load (bind time), we still have to manually release it from the renderable
	-- TODO: add font stamping support to composite instead of having the renderable do this at bind time
	gr:AddAsset(player, lod, "font", "${GetRMNameFont(?)}data/sceneassets/jerseyfonts/font_${db.player[?].kitNameFont}.ttf", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_PERM)
	gr:AddAsset(player, lod, "kitnumbers", "${GetRMNumberSet(?,0)}data/sceneassets/kitnumbers/kitnumbers_${db.player[?].kitNumberFont}_${db.player[?].kitNumberColor}.rx3;data/sceneassets/kitnumbers/kitnumbers_0_0.rx3")
	gr:AddAsset(player, lod, "shortsnumbers", "${GetRMNumberSet(?,1)}data/sceneassets/kitnumbers/kitnumbers_${db.player[?].shortsNumberFont}_${db.player[?].shortsNumberColor}.rx3;data/sceneassets/kitnumbers/kitnumbers_0_0.rx3")

	local faceGenTemplate = "${GetFaceTexTemplate(?)}"
	local faceSpecAoTemplate = "${GetFaceSpecAoTexTemplate(?)}"

	--FACE PARTS
	gr:AddAsset(player, lod, "facepart1", "${GetRMFaceTex(?)}data/sceneassets/genheadtex/skin_${db.player[?].headSkinToneType}_${db.player[?].headSkinType}${db.player[?].compsuffix}", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)
	gr:AddAsset(player, lod, "facepart2", "${GetRMFaceTex(?)}data/sceneassets/genheadtex/brow_${db.player[?].headSkinToneType}_${db.player[?].eyebrow}_${db.player[?].facialHairColor}${db.player[?].compsuffix}", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)
	gr:AddAsset(player, lod, "facepart3", "${GetRMFaceTex(?)}data/sceneassets/genheadtex/beard_${db.player[?].headSkinToneType}_${db.player[?].facialHairType}_${db.player[?].facialHairColor}${db.player[?].compsuffix}", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)
	gr:AddAsset(player, lod, "facepart4", "${GetRMFaceTex(?)}data/sceneassets/genheadtex/sideburn_${db.player[?].headSkinToneType}_${db.player[?].faceSideBurn}_${db.player[?].facialHairColor}${db.player[?].compsuffix}", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)
	--END FACE PARTS
	
	part = "facetex"
	gr:AddAssetEx(player, lod, "${GetFaceTextureOperation(?)}", part , faceGenTemplate)

	-- Describe texture composition in case we have to generate the texture, this material won't be created if no composition is needed.
	gr:CreateMaterial(player, lod, part, "texcompface.fx" )
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex0", "facepart1", "cm") -- base skin
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex1", "facepart2", "cm") -- eye brow
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex2", "facepart3", "cm") -- beard
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex3", "facepart4", "cm") -- sideburn

	gr:AddAsset(player, lod, "specpart", "${GetRMFaceBump(?)}data/sceneassets/heads/head_common_${db.player[?].gender}_textures.rx3", defaultpriority, ASSET_NO_COPY, ALLOCTYPE_TEMP_AUTO_RELEASE)

	part = "facespectex"
	gr:AddAssetEx(player, lod, "${GetFaceSpecTextureOperation(?)}", part, faceSpecAoTemplate)

	-- Describe texture composition in case we have to generate the texture, this material won't be created if no composition is needed.
	gr:CreateMaterial(player, lod, part, "texcompspec.fx" )
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex0", "specpart", "head_sk") -- base spec/ao
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex1", "facepart3", "cm") -- beard
	gr:SetTexture(player, lod, part, "textures", "texcomp_tex2", "facepart2", "cm") -- brow
	
	-- No lods for undergear
	gr:AddAsset(player, lod, "underarms", "data/sceneassets/body/underarms_0_${db.player[?].underarms}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "underneck", "data/sceneassets/body/underneck_0_${db.player[?].underneck}_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "undershorts", "data/sceneassets/body/undershorts_0_${db.player[?].undershorts}_${db.player[?].gender}.rx3")

	gr:AddAsset(player, lod, "warmup_top", "${GetRMBenchModel(?,1)}data/sceneassets/body/warmup_"..(lod).."_${db.player[?].cold}_0_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "warmup_bottom", "${GetRMBenchModel(?,2)}data/sceneassets/body/warmup_"..(lod).."_${db.player[?].cold}_1_${db.player[?].gender}.rx3")
	gr:AddAsset(player, lod, "warmuptextures", "${GetRMBench(?)}data/sceneassets/warmup/warmup_${db.player[?].cold}_0_textures.rx3")

	-- simple cloth assets
	local jerseyCloth = "${GetSimpleClothJersey(?)}"
	local shortsCloth = "${GetSimpleClothShorts(?)}"
	gr:AddAsset(player, lod, "jerseycloth", jerseyCloth)
	gr:AddAsset(player, lod, "shortscloth", shortsCloth)
	

	if (lod == 0) then
		gr:AddAsset(player, lod, "haircloth", "data/sceneassets/simplecloth/simhair_${db.player[?].hair}_${db.player[?].faceProxyHeadClass}_0.rx3;data/sceneassets/simplecloth/simhair_${db.player[?].generichair}_${db.player[?].genericfaceProxyHeadClass}_0.rx3")
	end

	if (lod == 0) then
		PlayerAssetHighLod(player, lod)
	elseif (lod == 1) then
		PlayerAssetLowLod(player, lod)
	elseif (lod == 2) then
		PlayerAssetLowLod(player, lod)
	elseif (lod == 3) then
		PlayerAssetShadow(player, lod)
	end

	if (lod < 3) then
		PlayerCommonBinding(player,lod)
	end

end

---------------------------------------------------------------------------------------------------
function PlayerAssetBind(player)
	PlayerAssetLod(player, 0)
	PlayerAssetLod(player, 1)
	PlayerAssetLod(player, 2)
	PlayerAssetLod(player, 3)

end












function GetRMNameFont(idx)
	local kitnamestring = ""
	
	--db.player[idx].classictournid
	if (db.player[idx].kitYear > 0) then
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_"..db.player[idx].classictournid.."_"..db.player[idx].speckitType..".ttf;"
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_0_"..db.player[idx].classictournid.."_0.ttf;"
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_"..db.player[idx].classictournid.."_0.ttf;"
	end
	
	
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_"..db.player[idx].tournidnum.."_"..db.player[idx].speckitType..".ttf;"
	if (db.player[idx].kitYear == 0) then
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_"..db.player[idx].defaulttournid.."_"..db.player[idx].speckitType..".ttf;"
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_0_"..db.player[idx].speckitType..".ttf;"
	end
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_"..db.player[idx].tournidnum.."_"..db.player[idx].kitType..".ttf;"
	if (db.player[idx].kitYear == 0) then
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_"..db.player[idx].defaulttournid.."_"..db.player[idx].kitType..".ttf;"
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_1_0_"..db.player[idx].kitType..".ttf;"
	end
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_0_"..db.player[idx].tournidnum.."_0.ttf;"
	if (db.player[idx].kitYear == 0) then
    kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_"..db.player[idx].tournidnum.."_0.ttf;"
    kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_"..db.player[idx].teamid.."_0_0_0.ttf;"
	if (db.player[idx].tournidnum == -1) then
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_0_"..db.player[idx].defaulttournid..".ttf;"
	else
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_"..db.player[idx].tournidnum.."_"..db.player[idx].defaulttournid..".ttf;"
	end
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_"..db.player[idx].defaulttournid.."_0.ttf;"
	kitnamestring = kitnamestring.."data/sceneassets/jerseyfonts/specificfont_0_0_0_0.ttf;"
	end
	return kitnamestring
end

function GetRMNumberSet(idx,short)
	local colour = 0
	local kitnumberstring = ""
	
	if (short == 0) then
	colour = db.player[idx].kitNumberColor
	else
	colour = db.player[idx].shortsNumberColor
	end
	
	--db.player[idx].classictournid
	if (db.player[idx].kitYear > 0) then
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_"..db.player[idx].classictournid.."_"..db.player[idx].speckitType..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_0_"..db.player[idx].classictournid.."_"..colour..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].classictournid.."_"..colour..".rx3;"
	end
	
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_"..db.player[idx].tournidnum.."_"..db.player[idx].speckitType..".rx3;"
	if (db.player[idx].kitYear == 0) then
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_"..db.player[idx].defaulttournid.."_"..db.player[idx].speckitType..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_0_"..db.player[idx].speckitType..".rx3;"
	end
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_"..db.player[idx].tournidnum.."_"..db.player[idx].kitType..".rx3;"
	if (db.player[idx].kitYear == 0) then
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_"..db.player[idx].defaulttournid.."_"..db.player[idx].kitType..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_"..(short+1).."_0_"..db.player[idx].kitType..".rx3;"
	end
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_0_"..db.player[idx].tournidnum.."_"..colour..".rx3;"
	if (db.player[idx].kitYear == 0) then
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].tournidnum.."_"..(colour+(short*100))..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].tournidnum.."_"..colour..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_"..db.player[idx].teamid.."_0_"..db.player[idx].kitYear.."_"..colour..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].defaulttournid.."_"..(colour+(short*100))..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].defaulttournid.."_"..colour..".rx3;"
	kitnumberstring = kitnumberstring.."data/sceneassets/kitnumbers/specifickitnumbers_0_0_"..db.player[idx].kitYear.."_"..colour..".rx3;"
	end
	return kitnumberstring 
end




repGenBoots = true

--FIFA 14 > ADAPT FOR 15
function getGenericBootReplacement(id,kitType)

if (playerBootFallback[id] ~= nil) then
if (playerBootFallback[id] ~= 0) then
return playerBootFallback[id]
end
end

--BLACK BOOTS FOR REFS
if (kitType == 5) then
local bootarray = {22,69,79,133,150,157,160,175,179,247}
local rboot = (id % #bootarray)+1
return bootarray[rboot]
end

local rand = (id%230)+21



if (rand == 34) then
rand = 23
end

if (rand == 35) then
rand = 23
end

if (rand == 59) then
rand = 23
end

if (rand == 60) then
rand = 23
end

if (rand == 61) then
rand = 23
end

if (rand == 62) then
rand = 23
end
if (rand == 126) then
rand = 23
end

if (rand == 127) then
rand = 23
end





return rand
end

--FIFA 15 DEMO ONLY
-- function getGenericBootReplacement(id,boot)
-- local rand = (id%6)+1
-- local bootarray = {131,185,25,40,33,44}
-- return bootarray[rand]
-- end




function disableGenericBootReplacement()
repGenBoots = false
end

genBootsPlayer = {}

function enablePlayerGenericBoot(id)
genBootsPlayer[id] = 1
end



function getPlayerGenericBoot(id)
if (genBootsPlayer[id] ~= nil) then
if (genBootsPlayer[id] == 1) then
return true
end
end

return false
end


--FIFA15VERSION
function GetRMBoot(idx,model)
	local bootstring = ""
	local tex = ""

	if (model == 1) then
	tex = "_textures"
	end
	
	if (repGenBoots or (db.player[idx].shoeType ~= 0)) then
	if (not getPlayerGenericBoot(db.player[idx].playerassetid)) then
	
	--bootstring = bootstring.."data/sceneassets/shoe/playershoe_0_0_"..db.player[idx].bootrand.."_0"..tex..".rx3;"
	
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_"..db.player[idx].speckitType.."_"..db.player[idx].tournid..""..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid..""..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_0_"..db.player[idx].tournid..""..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_0_"..db.player[idx].teamid.."_0_"..db.player[idx].tournid..""..tex..".rx3;"
	
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_0_0_0_"..db.player[idx].kitYearDecade..""..tex..".rx3;"
	
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_0_"..db.player[idx].teamid.."_0_0"..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_"..db.player[idx].speckitType.."_0"..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_"..db.player[idx].kitType.."_0"..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_0_0"..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_0_0_"..db.player[idx].tournid..""..tex..".rx3;"
	
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_0_"..db.player[idx].bootrand.."_0"..tex..".rx3;"
	bootstring = bootstring.."data/sceneassets/shoe/playershoe_"..db.player[idx].playerassetid.."_0_0_0"..tex..".rx3;"
	
	bootstring = bootstring.."data/sceneassets/shoelib/"..db.player[idx].bootname.."/shoe"..tex..".rx3;"
	end
	end
	
	return bootstring
end



	




function GetRMKit(idx,pos)
	local kitstring = ""
	
	local isfinal = getTournamentFinal(db.player[idx].tournid,db.player[idx].stadiumID,db.player[idx].crowdDistribution)
	
	if (db.player[idx].kitType ~= 5) then
	
	local speckitTypeItem = getIndividualKitPart(db.player[idx].speckitType,1)
	local kitTypeItem = getIndividualKitPart(db.player[idx].kitType,1)
	
	if (pos == 2) then
	speckitTypeItem = getIndividualKitPart(db.player[idx].speckitTypeShort,2)
	kitTypeItem = getIndividualKitPart(db.player[idx].kitType,2)
	end
	
	if (pos == 3) then
	speckitTypeItem = getIndividualKitPart(db.player[idx].speckitTypeSock,3)
	kitTypeItem = getIndividualKitPart(db.player[idx].kitType,3)
	end
	
	-- if (pos == 1) then
	-- kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_999_"..db.player[idx].tournid..".rx3;"
	-- end
	
	if (isfinal) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(speckitTypeItem+200).."_"..db.player[idx].tournid..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(db.player[idx].kitType+200).."_"..db.player[idx].tournid..".rx3;"
	end
	
	if (db.player[idx].kitYear > 0) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..speckitTypeItem.."_"..db.player[idx].classictournid..".rx3;"
	end
	
	--if (speckitTypeItem > -1) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(300000000+(speckitTypeItem*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournidkit..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(speckitTypeItem+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournidkit..".rx3;"
	if (db.player[idx].kit < 10000) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(20000+(speckitTypeItem*100)+db.player[idx].shirtid).."_"..db.player[idx].tournidkit..".rx3;"
	end
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+speckitTypeItem).."_"..db.player[idx].tournidkit..".rx3;" --F
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..speckitTypeItem.."_"..db.player[idx].tournidkit..".rx3;"

	-- if ((db.player[idx].kitYearDecade > 0) and (pos == 1)) then
	-- kitstring = kitstring.."data/sceneassets/kit/kit_9_2_1984.rx3;"
	-- end
	
	if ((db.player[idx].kitYearDecade > 0) and (classicGKMode)) then
	if (db.player[idx].speckitType == 2) then
	if (pos == 1) then
	kitstring = kitstring.."data/sceneassets/kit/kit_5002_2_0.rx3;"
	else
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_"..db.player[idx].tournidkit..".rx3;"
	end
	end
	end
	
	
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(300000000+(speckitTypeItem*1000000)+db.player[idx].playerassetid).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(speckitTypeItem+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(20000+(speckitTypeItem*100)+db.player[idx].shirtid).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+speckitTypeItem).."_0.rx3;" --F
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..speckitTypeItem.."_0.rx3;"
	--end

	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(300000000+(kitTypeItem*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournidkit..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(kitTypeItem+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournidkit..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(20000+(kitTypeItem*100)+db.player[idx].shirtid).."_"..db.player[idx].tournidkit..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+kitTypeItem).."_"..db.player[idx].tournidkit..".rx3;" --F
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..kitTypeItem.."_"..db.player[idx].tournidkit..".rx3;"

	-- if ((db.player[idx].kitYearDecade > 0) and (classicGKMode)) then
	-- if (pos == 1) then
	-- kitstring = kitstring.."data/sceneassets/kit/kit_5002_2_0.rx3;"
	-- else
	-- kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_"..db.player[idx].tournidkit..".rx3;"
	-- end
	-- end
	
	if not ((db.player[idx].kitYearDecade > 0) and (classicGKMode)) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(300000000+(kitTypeItem*1000000)+db.player[idx].playerassetid).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(kitTypeItem+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..(20000+(kitTypeItem*100)+db.player[idx].shirtid).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+kitTypeItem).."_0.rx3;" --F
	end
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..kitTypeItem.."_0.rx3;"
	
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].genkit.."_"..kitTypeItem.."_"..db.player[idx].kitYear..".rx3"
	end
	


	
	
	if (db.player[idx].kitType == 5) then
	
	--FOURTH OFFICIAL
	if ((db.player[idx].fourthofficialoption == 2) or ((db.player[idx].fourthofficialoption == 1) and (pos == 1))) then
	if (idx == 57) then
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_99_"..db.player[idx].tournidref..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_99_"..db.player[idx].defaulttournid..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_99_0.rx3;"
	end
	end
	
	kitstring = kitstring.."data/sceneassets/kit/specifickit_6004_"..db.player[idx].kitType.."_"..db.player[idx].tournidref.."_"..db.player[idx].homeKitTeamID.."_"..db.player[idx].awayKitTeamID..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_"..db.player[idx].tournidref..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournidref..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_"..db.player[idx].tournidref..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..db.player[idx].kitType.."_"..db.player[idx].tournidref..".rx3;"
	
	--kitstring = kitstring.."data/sceneassets/kit/specifickit_6004_"..db.player[idx].kitType.."_"..db.player[idx].kitYearDecade.."_"..db.player[idx].homeKitTeamID.."_"..db.player[idx].awayKitTeamID..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].kitYearDecade..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..db.player[idx].kitType.."_"..db.player[idx].kitYearDecade..".rx3;"
	
	kitstring = kitstring.."data/sceneassets/kit/specifickit_6004_"..db.player[idx].kitType.."_"..db.player[idx].defaulttournid.."_"..db.player[idx].homeKitTeamID.."_"..db.player[idx].awayKitTeamID..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_"..db.player[idx].defaulttournid..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].defaulttournid..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_"..db.player[idx].defaulttournid..".rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..db.player[idx].kitType.."_"..db.player[idx].defaulttournid..".rx3;"
	
	if ((db.player[idx].gender == 0) or (enableEAFemaleRefereeKits)) then
	if (db.player[idx].genkit > 6100) then
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].genkit.."_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].genkit.."_"..db.player[idx].kitType.."_0.rx3;"
	end
	end
	
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0.rx3;"
	
	
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..((db.player[idx].gender*100)+db.player[idx].kitType).."_0.rx3;"
	kitstring = kitstring.."data/sceneassets/kit/kit_6004_"..db.player[idx].kitType.."_0.rx3"
	end
	
	
	
	return kitstring
end


function GetRMSkin(idx)
	local skinstring = ""
	skinstring = skinstring.."data/sceneassets/body/playerskin_"..db.player[idx].playerassetid.."_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_"..db.player[idx].useWinterAcc.."_textures.rx3;"
	skinstring = skinstring.."data/sceneassets/body/playerskin_"..db.player[idx].playerassetid.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].useWinterAcc.."_textures.rx3;"
	skinstring = skinstring.."data/sceneassets/body/playerskin_"..db.player[idx].playerassetid.."_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_0_textures.rx3;"
	skinstring = skinstring.."data/sceneassets/body/playerskin_"..db.player[idx].playerassetid.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_textures.rx3;"
	skinstring = skinstring.."data/sceneassets/body/playerskin_"..db.player[idx].playerassetid.."_textures.rx3;"
	skinstring = skinstring.."data/sceneassets/body/playerskin_0_"..db.player[idx].kit.."_0_0_textures.rx3;"
	return skinstring
end








tournamentRefereeKitsCollar = {}

function assignTournamentRefereeKitCollar(tournament,collar)
tournamentRefereeKitsCollar[tournament] = collar
end



function getTournamentRefereeKitsCollar(tourn,id,teamtourn)

if (tournamentRefereeKitsCollar[tourn] ~= nil) then
return tournamentRefereeKitsCollar[tourn]
end

if (tournamentRefereeKitsCollar[teamtourn] ~= nil) then
return tournamentRefereeKitsCollar[teamtourn]
end

return id
end



gkPants = {}
gkPantsTraining = {}
gkPantsWinter = {}
gkPantsSnow = {}

function assignGKPants(id)
gkPants[id] = 1
end

function assignGKPantsTraining(id)
gkPantsTraining[id] = 1
end

function assignGKPantsWinter(id)
gkPantsWinter[id] = 1
end

function assignGKPantsSnow(id)
gkPantsSnow[id] = 1
end

function getGKPants(id,pant,tr,weather,winter)

if ((tr > 90) and (tr < 97)) then
if (gkPantsTraining[id] ~= nil) then
return gkPantsTraining[id]
end
end

if (weather == 2) then
if (gkPantsSnow[id] ~= nil) then
return gkPantsSnow[id]
end
end

if (winter == 1) then
if (gkPantsWinter[id] ~= nil) then
return gkPantsWinter[id]
end
end

if (gkPants[id] ~= nil) then
return gkPants[id]
end

return pant
end


playerFace = {}

function assignPlayerFace(id)
playerFace[id] = 0
end

function getPlayerFace(id,headtype)

if (playerFace[id] ~= nil) then
return playerFace[id]
end

return headtype
end


gkKits = {}

function assignGKKit(team,player,gk)

if (type(gk) == "number") then
assignGKKitPrecedence(team,player,1,{gk})
else
assignGKKitPrecedence(team,player,1,gk)
end


-- if (gkKits[team] == nil) then
-- gkKits[team] = {}
-- end

-- if (type(gk) == "number") then
-- gkKits[team][player] = gk
-- else
-- if (gkKits[team][player] == nil)then
-- gkKits[team][player] = gk[math.random(#gk)]
-- end
-- end

end

function getGKKit(team,player,home,away,gk,spec)

-- if (matchKit[team] ~= nil) then
-- if (matchKit[team][home] ~= nil) then
-- if (matchKit[team][home][away] ~= nil) then
-- if (matchKit[team][home][away][gk] ~= nil) then
-- return matchKit[team][home][away][gk]
-- end
-- end
-- end
-- end

-- if (swapKit[team] ~= nil) then
-- if (swapKit[team][gk] ~= nil) then
-- return swapKit[team][gk]
-- end
-- end

-- if (gkKits[team] ~= nil) then
-- if (gkKits[team][player] ~= nil) then
-- return gkKits[team][player]
-- end
-- end

return spec
end


--KIT DETAILS START

kitCollar = {}
kitNumberSet = {}
kitNumberColourShirt = {}
kitNumberColourShort = {}
kitNameFont = {}
kitNameColour = {}
kitFit = {}
kitNameCurve = {}


function assignKitDetails(team,kit,namefont,namecolour,lay,numberset,numbercolourshirt,numbercolourshort,fit,collar)

if (kitCollar[team] == nil) then
kitCollar[team] = {}
end

if (kitNumberSet[team] == nil) then
kitNumberSet[team] = {}
end

if (kitNumberColourShirt[team] == nil) then
kitNumberColourShirt[team] = {}
end

if (kitNumberColourShort[team] == nil) then
kitNumberColourShort[team] = {}
end

if (kitNameFont[team] == nil) then
kitNameFont[team] = {}
end

if (kitNameColour[team] == nil) then
kitNameColour[team] = {}
end

if (kitFit[team] == nil) then
kitFit[team] = {}
end

if (kitNameCurve[team] == nil) then
kitNameCurve[team] = {}
end


kitCollar[team][kit] = collar
kitNumberSet[team][kit] = numberset
kitNumberColourShirt[team][kit] = numbercolourshirt
kitNumberColourShort[team][kit] = numbercolourshort
kitNameFont[team][kit] = namefont

if (namecolour ~= -1) then
kitNameColour[team][kit] = hex(namecolour)
end

kitFit[team][kit] = fit
kitNameCurve[team][kit] = lay
end


kitCollarTournament = {}
kitNumberSetTournament = {}
kitNumberColourShirtTournament = {}
kitNumberColourShortTournament = {}
kitNameFontTournament = {}
kitNameColourTournament = {}
kitFitTournament = {}
kitNameCurveTournament = {}


function assignTournamentKitDetails(team,kit,tournament,namefont,namecolour,lay,numberset,numbercolourshirt,numbercolourshort,fit,collar)

if (kitCollarTournament[team] == nil) then
kitCollarTournament[team] = {}
end

if (kitNumberSetTournament[team] == nil) then
kitNumberSetTournament[team] = {}
end

if (kitNumberColourShirtTournament[team] == nil) then
kitNumberColourShirtTournament[team] = {}
end

if (kitNumberColourShortTournament[team] == nil) then
kitNumberColourShortTournament[team] = {}
end

if (kitNameFontTournament[team] == nil) then
kitNameFontTournament[team] = {}
end

if (kitNameColourTournament[team] == nil) then
kitNameColourTournament[team] = {}
end

if (kitFitTournament[team] == nil) then
kitFitTournament[team] = {}
end

if (kitNameCurveTournament[team] == nil) then
kitNameCurveTournament[team] = {}
end



if (kitCollarTournament[team][kit] == nil) then
kitCollarTournament[team][kit] = {}
end

if (kitNumberSetTournament[team][kit] == nil) then
kitNumberSetTournament[team][kit] = {}
end

if (kitNumberColourShirtTournament[team][kit] == nil) then
kitNumberColourShirtTournament[team][kit] = {}
end

if (kitNumberColourShortTournament[team][kit] == nil) then
kitNumberColourShortTournament[team][kit] = {}
end

if (kitNameFontTournament[team][kit] == nil) then
kitNameFontTournament[team][kit] = {}
end

if (kitNameColourTournament[team][kit] == nil) then
kitNameColourTournament[team][kit] = {}
end

if (kitFitTournament[team][kit] == nil) then
kitFitTournament[team][kit] = {}
end

if (kitNameCurveTournament[team][kit] == nil) then
kitNameCurveTournament[team][kit] = {}
end



kitCollarTournament[team][kit][tournament] = collar
kitNumberSetTournament[team][kit][tournament] = numberset
kitNumberColourShirtTournament[team][kit][tournament] = numbercolourshirt
kitNumberColourShortTournament[team][kit][tournament] = numbercolourshort
kitNameFontTournament[team][kit][tournament] = namefont

if (namecolour ~= -1) then
kitNameColourTournament[team][kit][tournament] = hex(namecolour)
end

kitFitTournament[team][kit][tournament] = fit
kitNameCurveTournament[team][kit][tournament] = lay
end



kitCollarBackup = {}
kitNumberSetShirtBackup = {}
kitNumberSetShortsBackup = {}
kitNumberColourShirtBackup = {}
kitNumberColourShortBackup = {}
kitNameFontBackup = {}
kitNameColourBackup = {}
kitFitBackup = {}
kitNameCurveBackup = {}


function assignKitDetailsBackup(team,kit,namefont,namecolour,lay,numbersetshirt,numbersetshorts,numbercolourshirt,numbercolourshort,fit,collar)

if (kitCollarBackup[team] == nil) then
kitCollarBackup[team] = {}
end

if (kitNumberSetShirtBackup[team] == nil) then
kitNumberSetShirtBackup[team] = {}
end

if (kitNumberSetShortsBackup[team] == nil) then
kitNumberSetShortsBackup[team] = {}
end

if (kitNumberColourShirtBackup[team] == nil) then
kitNumberColourShirtBackup[team] = {}
end

if (kitNumberColourShortBackup[team] == nil) then
kitNumberColourShortBackup[team] = {}
end

if (kitNameFontBackup[team] == nil) then
kitNameFontBackup[team] = {}
end

if (kitNameColourBackup[team] == nil) then
kitNameColourBackup[team] = {}
end

if (kitFitBackup[team] == nil) then
kitFitBackup[team] = {}
end

if (kitNameCurveBackup[team] == nil) then
kitNameCurveBackup[team] = {}
end


kitCollarBackup[team][kit] = collar
kitNumberSetShirtBackup[team][kit] = numbersetshirt
kitNumberSetShortsBackup[team][kit] = numbersetshorts
kitNumberColourShirtBackup[team][kit] = numbercolourshirt
kitNumberColourShortBackup[team][kit] = numbercolourshort
kitNameFontBackup[team][kit] = namefont

--if (namecolour ~= -1) then
kitNameColourBackup[team][kit] = namecolour --hex(namecolour)
--end

kitFitBackup[team][kit] = fit
kitNameCurveBackup[team][kit] = lay
end





function getKitCollar(team,kit,item,tournament,year,ctournament)

--classic+tourn
if (year > 0) then
if (kitCollarTournament[team] ~= nil) then
if (kitCollarTournament[team][kit] ~= nil) then
if ((kitCollarTournament[team][kit][ctournament] ~= nil) and (kitCollarTournament[team][kit][ctournament] ~= -1)) then
return kitCollarTournament[team][kit][ctournament]
end
end
end
end

if (kitCollarTournament[team] ~= nil) then
if (kitCollarTournament[team][kit] ~= nil) then
if ((kitCollarTournament[team][kit][tournament] ~= nil) and (kitCollarTournament[team][kit][tournament] ~= -1)) then
return kitCollarTournament[team][kit][tournament]
end
end
end

if (year == 0) then

if (kitCollar[team] ~= nil) then
if ((kitCollar[team][kit] ~= nil) and (kitCollar[team][kit] ~= -1)) then
return kitCollar[team][kit]
end
end

--backup
if (kitCollarBackup[team] ~= nil) then
if ((kitCollarBackup[team][kit] ~= nil) and (kitCollarBackup[team][kit] ~= -1)) then
return kitCollarBackup[team][kit]
end
end

end

return item
end

function getKitNumberSet(team,kit,item,tournament,teamdef,year,ctournament,stype)

--classic+tourn
if (year > 0) then
if (kitNumberSetTournament[team] ~= nil) then
if (kitNumberSetTournament[team][kit] ~= nil) then
if ((kitNumberSetTournament[team][kit][ctournament] ~= nil) and (kitNumberSetTournament[team][kit][ctournament] ~= -1)) then
return kitNumberSetTournament[team][kit][ctournament]
end
end
end
end

if (kitNumberSetTournament[team] ~= nil) then
if (kitNumberSetTournament[team][kit] ~= nil) then
if ((kitNumberSetTournament[team][kit][tournament] ~= nil) and (kitNumberSetTournament[team][kit][tournament] ~= -1)) then
return kitNumberSetTournament[team][kit][tournament]
end
end
end


if (year == 0) then

if (kitNumberSet[team] ~= nil) then
if ((kitNumberSet[team][kit] ~= nil) and (kitNumberSet[team][kit] ~= -1)) then
return kitNumberSet[team][kit]
end
end

--backup
if (stype == 1) then
if (kitNumberSetShirtBackup[team] ~= nil) then
if ((kitNumberSetShirtBackup[team][kit] ~= nil) and (kitNumberSetShirtBackup[team][kit] ~= -1)) then
return kitNumberSetShirtBackup[team][kit]
end
end
else
if (kitNumberSetShortsBackup[team] ~= nil) then
if ((kitNumberSetShortsBackup[team][kit] ~= nil) and (kitNumberSetShortsBackup[team][kit] ~= -1)) then
return kitNumberSetShortsBackup[team][kit]
end
end
end

end

return item
end

function getKitNumberColourShirt(team,kit,item,tournament,year,ctournament)

--classic+tourn
if (year > 0) then
if (kitNumberColourShirtTournament[team] ~= nil) then
if (kitNumberColourShirtTournament[team][kit] ~= nil) then
if ((kitNumberColourShirtTournament[team][kit][ctournament] ~= nil) and (ckitNumberColourShirtTournament[team][kit][tournament] ~= -1)) then
return kitNumberColourShirtTournament[team][kit][ctournament]
end
end
end
end

if (kitNumberColourShirtTournament[team] ~= nil) then
if (kitNumberColourShirtTournament[team][kit] ~= nil) then
if ((kitNumberColourShirtTournament[team][kit][tournament] ~= nil) and (kitNumberColourShirtTournament[team][kit][tournament] ~= -1)) then
return kitNumberColourShirtTournament[team][kit][tournament]
end
end
end

if (year == 0) then

if (kitNumberColourShirt[team] ~= nil) then
if ((kitNumberColourShirt[team][kit] ~= nil) and (kitNumberColourShirt[team][kit] ~= -1)) then
return kitNumberColourShirt[team][kit]
end
end

--backup
if (kitNumberColourShirtBackup[team] ~= nil) then
if ((kitNumberColourShirtBackup[team][kit] ~= nil) and (kitNumberColourShirtBackup[team][kit] ~= -1)) then
return kitNumberColourShirtBackup[team][kit]
end
end

end

return item
end

function getKitNumberColourShort(team,kit,item,tournament,year,ctournament)

--classic+tourn
if (year > 0) then
if (kitNumberColourShortTournament[team] ~= nil) then
if (kitNumberColourShortTournament[team][kit] ~= nil) then
if ((kitNumberColourShortTournament[team][kit][ctournament] ~= nil) and (kitNumberColourShortTournament[team][kit][ctournament] ~= -1)) then
return kitNumberColourShortTournament[team][kit][ctournament]
end
end
end
end

if (kitNumberColourShortTournament[team] ~= nil) then
if (kitNumberColourShortTournament[team][kit] ~= nil) then
if ((kitNumberColourShortTournament[team][kit][tournament] ~= nil) and (kitNumberColourShortTournament[team][kit][tournament] ~= -1)) then
return kitNumberColourShortTournament[team][kit][tournament]
end
end
end

if (year == 0) then

if (kitNumberColourShort[team] ~= nil) then
if ((kitNumberColourShort[team][kit] ~= nil) and (kitNumberColourShort[team][kit] ~= -1)) then
return kitNumberColourShort[team][kit]
end
end

--backup
if (kitNumberColourShortBackup[team] ~= nil) then
if ((kitNumberColourShortBackup[team][kit] ~= nil) and (kitNumberColourShortBackup[team][kit] ~= -1)) then
return kitNumberColourShortBackup[team][kit]
end
end


end

return item
end

function getKitNameFont(team,kit,item,tournament,teamdef,year,ctournament)

--classic+tourn
if (year > 0) then
if (kitNameFontTournament[team] ~= nil) then
if (kitNameFontTournament[team][kit] ~= nil) then
if ((kitNameFontTournament[team][kit][ctournament] ~= nil) and (kitNameFontTournament[team][kit][ctournament] ~= -1)) then
return kitNameFontTournament[team][kit][ctournament]
end
end
end
end

if (kitNameFontTournament[team] ~= nil) then
if (kitNameFontTournament[team][kit] ~= nil) then
if ((kitNameFontTournament[team][kit][tournament] ~= nil) and (kitNameFontTournament[team][kit][tournament] ~= -1)) then
return kitNameFontTournament[team][kit][tournament]
end
end
end


if (year == 0) then

if (kitNameFont[team] ~= nil) then
if ((kitNameFont[team][kit] ~= nil) and (kitNameFont[team][kit] ~= -1)) then
return kitNameFont[team][kit]
end
end

--backup
if (kitNameFontBackup[team] ~= nil) then
if ((kitNameFontBackup[team][kit] ~= nil) and (kitNameFontBackup[team][kit] ~= -1)) then
return kitNameFontBackup[team][kit]
end
end

end

return item
end

function getKitNameColour(team,kit,item,tournament,year,ctournament,numcolour,gentournament)

--classic+tourn
if (year > 0) then
if (kitNameColourTournament[team] ~= nil) then
if (kitNameColourTournament[team][kit] ~= nil) then
if ((kitNameColourTournament[team][kit][ctournament] ~= nil) and (kitNameColourTournament[team][kit][ctournament] ~= -1)) then
return kitNameColourTournament[team][kit][ctournament]
end
end
end
end

if (kitNameColourTournament[team] ~= nil) then
if (kitNameColourTournament[team][kit] ~= nil) then
if ((kitNameColourTournament[team][kit][tournament] ~= nil) and (kitNameColourTournament[team][kit][tournament] ~= -1)) then
return kitNameColourTournament[team][kit][tournament]
end
end
end

if (kitNameColourTournamentGeneric[tournament] ~= nil) then
if ((kitNameColourTournamentGeneric[tournament][numcolour] ~= nil) and (kitNameColourTournamentGeneric[tournament][numcolour] ~= -1)) then
return kitNameColourTournamentGeneric[tournament][numcolour]
end
end

if (year == 0) then

if (kitNameColour[team] ~= nil) then
if ((kitNameColour[team][kit] ~= nil) and (kitNameColour[team][kit] ~= -1)) then
return kitNameColour[team][kit]
end
end

if (kitNameColourTournamentGeneric[gentournament] ~= nil) then
if ((kitNameColourTournamentGeneric[gentournament][numcolour] ~= nil) and (kitNameColourTournamentGeneric[gentournament][numcolour] ~= -1)) then
return kitNameColourTournamentGeneric[gentournament][numcolour]
end
end

--backup
if (kitNameColourBackup[team] ~= nil) then
if ((kitNameColourBackup[team][kit] ~= nil) and (kitNameColourBackup[team][kit] ~= -1)) then
return kitNameColourBackup[team][kit]
end
end

end

return item
end

function getKitFit(team,kit,item,tournament,player,year,ctournament)

if (globalJerseyFit ~= nil) then
return globalJerseyFit
end

--classic+tourn
if (year > 0) then
if (kitFitTournament[team] ~= nil) then
if (kitFitTournament[team][kit] ~= nil) then
if ((kitFitTournament[team][kit][ctournament] ~= nil) and (kitFitTournament[team][kit][ctournament] ~= -1)) then
return kitFitTournament[team][kit][ctournament]
end
end
end
end

if (kitFitTournament[team] ~= nil) then
if (kitFitTournament[team][kit] ~= nil) then
if ((kitFitTournament[team][kit][tournament] ~= nil) and (kitFitTournament[team][kit][tournament] ~= -1)) then
return kitFitTournament[team][kit][tournament]
end
end
end

if (year == 0) then

if (kitFit[team] ~= nil) then
if ((kitFit[team][kit] ~= nil) and (kitFit[team][kit] ~= -1)) then
return kitFit[team][kit]
end
end

end

if (kitFitPlayer[player] ~= nil) then
return kitFitPlayer[player]
end

return item
end





function getKitNameCurve(team,kit,lay,tournament,year,ctournament)

--classic+tourn
if (year > 0) then
if (kitNameCurveTournament[team] ~= nil) then
if (kitNameCurveTournament[team][kit] ~= nil) then
if ((kitNameCurveTournament[team][kit][ctournament] ~= nil) and (kitNameCurveTournament[team][kit][ctournament] ~= -1)) then
return kitNameCurveTournament[team][kit][ctournament]
end
end
end
end

if (kitNameCurveTournament[team] ~= nil) then
if (kitNameCurveTournament[team][kit] ~= nil) then
if ((kitNameCurveTournament[team][kit][tournament] ~= nil) and (kitNameCurveTournament[team][kit][tournament] ~= -1)) then
return kitNameCurveTournament[team][kit][tournament]
end
end
end

if (kitNameCurveTournamentTeam[team] ~= nil) then
if ((kitNameCurveTournamentTeam[team][tournament] ~= nil) and (kitNameCurveTournamentTeam[team][tournament] ~= -1)) then
return kitNameCurveTournamentTeam[team][tournament]
end
end

if (year == 0) then

if (kitNameCurve[team] ~= nil) then
if ((kitNameCurve[team][kit] ~= nil) and (kitNameCurve[team][kit] ~= -1)) then
return kitNameCurve[team][kit]
end
end

--backup
if (kitNameCurveBackup[team] ~= nil) then
if ((kitNameCurveBackup[team][kit] ~= nil) and (kitNameCurveBackup[team][kit] ~= -1)) then
return kitNameCurveBackup[team][kit]
end
end

end

return lay

end



function getKitNameVisible(team,tournament,vis)

if (kitNameVisibleTournamentTeam[team] ~= nil) then
if ((kitNameVisibleTournamentTeam[team][tournament] ~= nil) and (kitNameVisibleTournamentTeam[team][tournament] ~= -1)) then
return kitNameVisibleTournamentTeam[team][tournament]
end
end

return vis

end



kitNameCurveTournamentTeam = {}

function assignTeamTournamentNameLayout(team,tourn,nametype)

if (kitNameCurveTournamentTeam[team] == nil) then
kitNameCurveTournamentTeam[team] = {}
end

kitNameCurveTournamentTeam[team][tourn] = nametype

end


kitNameVisibleTournamentTeam = {}

function assignTeamTournamentNameVisible(team,tourn,vis)

if (kitNameVisibleTournamentTeam[team] == nil) then
kitNameVisibleTournamentTeam[team] = {}
end

kitNameVisibleTournamentTeam[team][tourn] = nametype

end


--KIT DETAILS END


jerseyTuck = {}
jerseyTuckGlobal = nil

function setJerseyTuck(player,option)

if (type(option) == "number") then
jerseyTuck[player] = option
else
jerseyTuck[player] = option[math.random(#option)]
end

--jerseyTuck[player] = tuck
end

function setJerseyTuckGlobal(option)

if (type(option) == "number") then
jerseyTuckGlobal = option
else
jerseyTuckGlobal = option[math.random(#option)]
end

--jerseyTuck[player] = tuck
end

function getJerseyTuck(player,tuck)

if (jerseyTuck[player] ~= nil) then
return jerseyTuck[player]
end

if (jerseyTuckGlobal ~= nil) then
return jerseyTuckGlobal
end

return tuck
end


sockHeight = {}

function setSockHeight(player,sock)
sockHeight[player] = sock
end

function getSockHeight(player,sock)

if (sockHeight[player] ~= nil) then
return sockHeight[player]
end

return sock
end



matchKit = {}
matchKitTourn = {}

function assignGameKit(team,home,away,type1,type2)

if (matchKit[team] == nil) then
matchKit[team] = {}
end

if (matchKit[team][home] == nil) then
matchKit[team][home] = {}
end

if (matchKit[team][home][away] == nil) then
matchKit[team][home][away] = {}
end

if (type(type2) == "number") then
matchKit[team][home][away][type1] = type2
else
if (matchKit[team][home][away][type1] == nil) then
matchKit[team][home][away][type1] = type2[math.random(#type2)]
end
end

end

function assignGameKitTournament(team,home,away,tourn,type1,type2)

if (matchKitTourn[team] == nil) then
matchKitTourn[team] = {}
end

if (matchKitTourn[team][home] == nil) then
matchKitTourn[team][home] = {}
end

if (matchKitTourn[team][home][away] == nil) then
matchKitTourn[team][home][away] = {}
end

if (matchKitTourn[team][home][away][tourn] == nil) then
matchKitTourn[team][home][away][tourn] = {}
end

if (type(type2) == "number") then
matchKitTourn[team][home][away][tourn][type1] = type2
else
if (matchKitTourn[team][home][away][tourn][type1] == nil) then
matchKitTourn[team][home][away][tourn][type1] = type2[math.random(#type2)]
end
end

end

function getGameKit(team,home,away,tourn,type1,type2)

if (matchKitTourn[team] ~= nil) then
if (matchKitTourn[team][home] ~= nil) then
if (matchKitTourn[team][home][away] ~= nil) then
if (matchKitTourn[team][home][away][tourn] ~= nil) then
if (matchKitTourn[team][home][away][tourn][type1] ~= nil) then
return matchKitTourn[team][home][away][tourn][type1]
end
end
end
end
end

if (matchKit[team] ~= nil) then
if (matchKit[team][home] ~= nil) then
if (matchKit[team][home][away] ~= nil) then
if (matchKit[team][home][away][type1] ~= nil) then
return matchKit[team][home][away][type1]
end
end
end
end

-- if (swapKit[team] ~= nil) then
-- if (swapKit[team][type1] ~= nil) then
-- return swapKit[team][type1]
-- end
-- end

return type2
end


function getSwapKit(team,type1,tourn)

-- if (swapKitSet[team] ~= nil) then
-- if (swapKitSet[team][kitsetactiveid] ~= nil) then
-- if (swapKitSet[team][kitsetactiveid][type1] ~= nil) then
-- return swapKitSet[team][kitsetactiveid][type1]
-- end
-- end
-- end

if (swapKitTourn[team] ~= nil) then
if (swapKitTourn[team][tourn] ~= nil) then
if (swapKitTourn[team][tourn][type1] ~= nil) then
return swapKitTourn[team][tourn][type1]
end
end
end

if (swapKit[team] ~= nil) then
if (swapKit[team][type1] ~= nil) then
return swapKit[team][type1]
end
end

return type1
end


function hex(s)

return tonumber(s,16) + 4278190080

end




--nameColourCodes = {"d5d9d5", "0d0c0d", "0046b0", "a00005", "e8d628", "007a00", "f88500", "7a19b8", "553210", "ed80b0", "750e05", "7dc1f0", "001450", "a0a2a0", "c5c965", "98864d", "f8c932", "c53232", "003c00"}


kitFitPlayer = {}

function setJerseyFit(player,fit)
kitFitPlayer[player] = fit
end




winterAccessoriesRef = nil

function useGlobalRefereeWinterAccessories(option)
winterAccessoriesRef = option
end

function getRefereeWinterAccessories(option)

if (winterAccessoriesRef ~= nil) then
return winterAccessoriesRef
end

return option
end


globalJerseyFit = nil

function useGlobalJerseyFit(option)
globalJerseyFit = option
end


swapKit = {}
swapKitTourn = {}
--swapKitSet = {}

function swapTeamKit(team,type1,type2)

if (swapKit[team] == nil) then
swapKit[team] = {}
end

if (type(type2) == "number") then
swapKit[team][type1] = type2
else
if (swapKit[team][type1] == nil) then
swapKit[team][type1] = type2[math.random(#type2)]
end
end

end

function swapTeamKitTournament(team,tourn,type1,type2)

if (swapKitTourn[team] == nil) then
swapKitTourn[team] = {}
end

if (swapKitTourn[team][tourn] == nil) then
swapKitTourn[team][tourn] = {}
end

if (type(type2) == "number") then
swapKitTourn[team][tourn][type1] = type2
else
if (swapKitTourn[team][tourn][type1] == nil) then
swapKitTourn[team][tourn][type1] = type2[math.random(#type2)]
end
end

end

function swapTeamKitSet(team,set,type1,type2)

if (kitsetactiveid[set] ~= nil) then
if (kitsetactiveid[set] == 1) then
swapTeamKit(team,type1,type2)
end
end

-- if (swapKitSet[team] == nil) then
-- swapKitSet[team] = {}
-- end

-- if (swapKitSet[team][set] == nil) then
-- swapKitSet[team][set] = {}
-- end

-- if (type(type2) == "number") then
-- swapKitSet[team][set][type1] = type2
-- else
-- if (swapKitSet[team][set][type1] == nil) then
-- swapKitSet[team][set][type1] = type2[math.random(#type2)]
-- end
-- end

end

function swapTeamKitTournamentSet(team,tourn,set,type1,type2)

if (kitsetactiveid[set] ~= nil) then
if (kitsetactiveid[set] == 1) then
swapTeamKitTournament(team,tourn,type1,type2)
end
end

end


fixGenGK = true

function disableOutfieldFontForGK()
fixGenGK = false
end


undershortsPlayer = {}
undershortsTeam = {}

function setUndershorts(player,option)
undershortsPlayer[player] = option
end

function setTeamUndershorts(team,option)
undershortsTeam[team] = option
end


function getUndershorts(player,option,year,team)

if ((year <= classicKitUndershortsYear) and (year > 0)) then
return -1
end

if (globalundershort ~= -1) then
return globalundershort
end

if (undershortsTeam[team] ~= nil) then
return undershortsTeam[team] - 1
end

if (undershortsPlayer[player] ~= nil) then
return undershortsPlayer[player] - 1
end

return option
end


function GetRMFaceTex(idx)
	local hpart = ""
	
	-- hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_"..db.player[idx].kityear.."_textures.rx3;"
	-- hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_"..(db.player[idx].kityear-1).."_textures.rx3;"
	-- hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_"..(db.player[idx].kityear-2).."_textures.rx3;"
	-- hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_"..(db.player[idx].kityear-3).."_textures.rx3;"
	-- hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_"..db.player[idx].tournid.."_textures.rx3;"
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_textures.rx3;"
	end
	
	hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/faces/specificface_"..db.player[idx].playerassetid.."_0_textures.rx3;"
	hpart = hpart.."data/sceneassets/faces/specificface_0_"..db.player[idx].teamid.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/faces/face_"..db.player[idx].playerassetid.."_0_0_0_0_0_0_0_0_textures.rx3;"
	if(db.player[idx].isVirtualPro == 0) then
	hpart = hpart.."data/sceneassets/faces/face_"..db.player[idx].faceType.."_"..db.player[idx].faceProxyHeadClass.."_0_"..db.player[idx].eyebrow.."_"..db.player[idx].faceSideBurn.."_"..db.player[idx].facialHairColor.."_"..db.player[idx].facialHairType.."_"..db.player[idx].headSkinType.."_"..db.player[idx].headSkinToneType.."_textures.rx3;"
	end
	return hpart
end

function GetRMHairTex(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_textures.rx3;"
	end
	
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_0_textures.rx3;"
	hpart = hpart.."data/sceneassets/hair/specifichair_0_"..db.player[idx].teamid.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/hair/hair_"..db.player[idx].playerassetid.."_0_textures.rx3;"
	return hpart
end

function GetRMEyeTex(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/heads/specificeyes_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_textures.rx3;"
	end
	
	hpart = hpart.."data/sceneassets/heads/specificeyes_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/heads/specificeyes_"..db.player[idx].playerassetid.."_0_textures.rx3;"
	hpart = hpart.."data/sceneassets/heads/specificeyes_0_"..db.player[idx].teamid.."_textures.rx3;"
	hpart = hpart.."data/sceneassets/heads/eyes_"..db.player[idx].playerassetid.."_0_textures.rx3;"
	return hpart
end

function GetRMHairMod(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid..".rx3;"
	end
	
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand..".rx3;"
	hpart = hpart.."data/sceneassets/hair/specifichair_"..db.player[idx].playerassetid.."_0.rx3;"
	hpart = hpart.."data/sceneassets/hair/specifichair_0_"..db.player[idx].teamid..".rx3;"
	hpart = hpart.."data/sceneassets/hair/hair_"..db.player[idx].playerassetid.."_0_0.rx3;"
	return hpart
end

function GetRMFaceMod(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid..".rx3;"
	end
	
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand..".rx3;"
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_0.rx3;"
	hpart = hpart.."data/sceneassets/heads/specifichead_0_"..db.player[idx].teamid..".rx3;"
	hpart = hpart.."data/sceneassets/heads/head_"..db.player[idx].playerassetid.."_0.rx3;"
	return hpart
end

function GetRMHairModLod(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/hairlod/specifichairlod_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid..".rx3;"
	end
	
	hpart = hpart.."data/sceneassets/hairlod/specifichairlod_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand..".rx3;"
	hpart = hpart.."data/sceneassets/hairlod/specifichairlod_"..db.player[idx].playerassetid.."_0.rx3;"
	hpart = hpart.."data/sceneassets/hairlod/specifichairlod_0_"..db.player[idx].teamid..".rx3;"
	hpart = hpart.."data/sceneassets/hairlod/hairlod_"..db.player[idx].playerassetid.."_0_0.rx3;"
	return hpart
end

function GetRMFaceBump(idx)
	local hpart = ""
	
	if (db.player[idx].teamid > 3) then
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_"..db.player[idx].teamid.."_bump.rx3;"
	end
	
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_"..db.player[idx].facerand.."_bump.rx3;"
	hpart = hpart.."data/sceneassets/heads/specifichead_"..db.player[idx].playerassetid.."_0_bump.rx3;"
	hpart = hpart.."data/sceneassets/heads/specifichead_0_"..db.player[idx].teamid.."_bump.rx3;"
	hpart = hpart.."data/sceneassets/heads/head_"..db.player[idx].playerassetid.."_bump.rx3;"
	return hpart
end


kitBottomTournament = {}

function assignTeamTournamentShorts(team,kit,tournament,bottom)

if (kitBottomTournament[team] == nil) then
kitBottomTournament[team] = {}
end

if (kitBottomTournament[team][kit] == nil) then
kitBottomTournament[team][kit] = {}
end

kitBottomTournament[team][kit][tournament] = bottom

end


function getTournamentShorts(team,kit,tournament,bottom)

if (kitBottomTournament[team] ~= nil) then
if (kitBottomTournament[team][kit] ~= nil) then
if (kitBottomTournament[team][kit][tournament] ~= nil) then
return kitBottomTournament[team][kit][tournament]
end
end
end


return bottom
end





playerBoot = {}
playerBootTeam = {}
--playerBootTournament = {}
playerBootFallback = {}

function assignPlayerShoe(id,boot)

playerBoot[id] = boot

end

function assignPlayerShoeTeam(id,team,boot)

if (playerBootTeam[id] == nil) then
playerBootTeam[id] = {}
end

playerBootTeam[id][team] = boot

end


function getPlayerShoe(id,team,boot)

if (playerBootTeam[id] ~= nil) then
if (playerBootTeam[id][team] ~= nil) then
return playerBootTeam[id][team]
end
end

if (playerBoot[id] ~= nil) then
return playerBoot[id]
end

return boot
end

function assignPlayerShoeFallback(id,boot)

playerBootFallback[id] = boot

end




function GetRMBench(idx)
	local kitstring = ""
	
	local name = "bib"
	
	local ven = 0
	
	if (db.player[idx].teamside == 1) then
	ven = 100
	end
	
	if (db.player[idx].cold == 1) then
	name = "tracksuit"
	end
	
	if ((GetRMTracksuitType(idx) == false) or (db.player[idx].cold == 0)) then
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].bibType.."_"..db.player[idx].tournid.."_textures.rx3;" --CHECK IF CAUSES ANY PROBLEMS
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..(db.player[idx].outfieldKitType+ven).."_"..db.player[idx].tournid.."_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..ven.."_"..db.player[idx].tournid.."_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_"..db.player[idx].tournid.."_textures.rx3;"
	--kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_textures.rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..db.player[idx].bibType.."_"..db.player[idx].tournid.."_textures.rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_"..db.player[idx].tournid.."_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_0_"..db.player[idx].tournid.."_textures.rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].bibType.."_0_textures.rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..(db.player[idx].outfieldKitType+ven).."_0_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..ven.."_0_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_0_textures.rx3;"
	--kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_textures.rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_0_0_textures.rx3;"
	
	if (db.player[idx].cold == 1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_0_textures.rx3;"
	else
	if (db.player[idx].bibType ~= -1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..db.player[idx].bibType.."_0_textures.rx3;"
	end
	if (db.player[idx].bibType == -1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_0_textures.rx3;"
	end
	end
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_0_0_textures.rx3;"
	
	end

	return kitstring
end




function GetRMBenchModel(idx,filetype)
	local kitstring = ""
	
	local name = "bib"
	
	local ven = 0
	
	if (db.player[idx].teamside == 1) then
	ven = 100
	end
	
	if (db.player[idx].cold == 1) then
	name = "tracksuit"
	end
	
	
	if ((GetRMTracksuitType(idx) == false) or (db.player[idx].cold == 0)) then
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].bibType.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;" --CHECK IF CAUSES ANY PROBLEMS
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..(db.player[idx].outfieldKitType+ven).."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..ven.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	--kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..db.player[idx].bibType.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_0_"..db.player[idx].tournid.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].bibType.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..(db.player[idx].outfieldKitType+ven).."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..ven.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].outfieldKitType.."_"..db.player[idx].gender.."_"..filetype..".rx3;"
	--kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_"..db.player[idx].kit.."_0_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	if (db.player[idx].cold == 1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	else
	if (db.player[idx].bibType ~= -1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..db.player[idx].bibType.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	end
	if (db.player[idx].bibType == -1) then
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_"..ven.."_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	end
	end
	
	kitstring = kitstring.."data/sceneassets/warmup/"..name.."_0_0_0_"..db.player[idx].gender.."_"..filetype..".rx3;"
	
	end

	return kitstring
end




-- Defaults to the vanilla kitnumbers_X_Y.rx3 identifier scheme so numbers still
-- render correctly even if assignments/general.lua fails to load or load order
-- shifts — useOriginalKitNumberIdentifier() is a no-op here but kept for the
-- custom "numbers_font_color_digit" scheme via disableOriginalKitNumberIdentifier().
newNumberType = false


function useOriginalKitNumberIdentifier()
newNumberType = false
end

function disableOriginalKitNumberIdentifier()
newNumberType = true
end


function GetRMNumberStringTens()

if (newNumberType) then
return "_${db.player[?].kitNumberTens}."
end

return "numbers_${db.player[?].kitNumberFont}_${db.player[?].kitNumberColor}_${db.player[?].kitNumberTens}"
end


function GetRMNumberStringUnits()

if (newNumberType) then
return "_${db.player[?].kitNumberUnits}."
end

return "numbers_${db.player[?].kitNumberFont}_${db.player[?].kitNumberColor}_${db.player[?].kitNumberUnits}"
end


function GetRMNumberStringTensShorts()

if (newNumberType) then
return "_${db.player[?].kitNumberTens}."
end

return "numbers_${db.player[?].shortsNumberFont}_${db.player[?].shortsNumberColor}_${db.player[?].kitNumberTens}"
end


function GetRMNumberStringUnitsShorts()

if (newNumberType) then
return "_${db.player[?].kitNumberUnits}."
end

return "numbers_${db.player[?].shortsNumberFont}_${db.player[?].shortsNumberColor}_${db.player[?].kitNumberUnits}"
end


trackSuitMode = false
bibMode = false
recolourTracksuits = false

teamTracksuit = {}
leagueTracksuit = {}

function GetRMTracksuitOption()

if ((trackSuitMode) or (bibMode)) then
return 1
end

return 2
end

function GetRMBibOption(x)

if (bibMode) then
return 1
end

return x
end


function activateTracksuitMode()
trackSuitMode = true
end

function activateBibMode()
bibMode = true
end

function disableAutomaticTracksuits()
recolourTracksuits = true
end

function GetRMTracksuitType(idx)

if (teamTracksuit[db.player[idx].teamid] ~= nil) then
return (teamTracksuit[db.player[idx].teamid] == 1)
end

if (leagueTracksuit[db.player[idx].defaulttournid] ~= nil) then
return (leagueTracksuit[db.player[idx].defaulttournid] == 1)
end

return recolourTracksuits
end

function setTeamTracksuitType(team,option)
teamTracksuit[team] = option
end

function setLeagueTracksuitType(league,option)
leagueTracksuit[league] = option
end




classicKitUndershirtYear = 0
classicKitUndershortsYear = 0
classicKitCaptainArmbandYear = 0
classicKitShortSleevesGKYear = 0
classicKitShortSleevesOutfieldYear = 0

function removeClassicKitUndershirt(year)
classicKitUndershirtYear = year
end

function removeClassicKitUndershorts(year)
classicKitUndershortsYear = year
end

function removeClassicKitCaptainArmband(year)
classicKitCaptainArmbandYear = year
end

function removeClassicKitShortSleevesGK(year)
classicKitShortSleevesGKYear = year
end

function removeClassicKitShortSleevesOutfield(year)
classicKitShortSleevesOutfieldYear = year
end


tournClone = {}

function copyTournamentNameAndNumberAssets(old,new)
tournClone[old] = new
end

function getCloneTournamentNumbers(old)

if (tournClone[old] ~= nil) then
return tournClone[old]
end

return old
end


tournCloneKit = {}
tournCloneKitLeague = {}

function copyTournamentKitAssets(old,new)
tournCloneKit[old] = new
end

function copyTournamentKitAssetsByLeague(old,new,league)

if (tournCloneKitLeague[old] == nil) then
tournCloneKitLeague[old] = {}
end

tournCloneKitLeague[old][league] = new
end

function getCloneTournamentKits(old,team)

if (tournCloneKitLeague[old] ~= nil) then
if (tournCloneKitLeague[old][teamTournament[team]] ~= nil) then
return tournCloneKitLeague[old][teamTournament[team]]
end
end


if (tournCloneKit[old] ~= nil) then
return tournCloneKit[old]
end

return old
end


tournCloneKitRef = {}

function copyTournamentRefereeKitAssets(old,new)
tournCloneKitRef[old] = new
end

function getCloneTournamentRefereeKits(old)

if (tournCloneKitRef[old] ~= nil) then
return tournCloneKitRef[old]
end

return old
end


isGK = {}

function identifyGK(id)
isGK[id] = 1
end

function isPlayerGK(id)

if (isGK[id] == 1) then
return true
end

return false
end


futKits = {}
-- futKits[0] = nil
-- futKits[1] = nil
-- futKits[3] = nil

function restrictFUTCustomKits(h,a,t)
futKits[0] = h
futKits[1] = a
futKits[3] = t
end



-- function GetRMShirtBNM(idx)
	-- local kitstring = ""
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificjersey_"..db.player[idx].kit.."_"..db.player[idx].specKitType.."_"..db.player[idx].tournid.."_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificjersey_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificjersey_"..db.player[idx].kit.."_"..db.player[idx].specKitType.."_0_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificjersey_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_bnm.rx3;"
	
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificjersey_"..db.player[idx].kit.."_0_0_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_bnm.rx3;"
	-- return kitstring
-- end

-- function GetRMShortsBNM(idx)
	-- local kitstring = ""
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].specKitType.."_"..db.player[idx].tournid.."_"..db.player[idx].shortstyle.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..db.player[idx].shortstyle.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].specKitType.."_0_"..db.player[idx].shortstyle.."_bnm.rx3;"
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..db.player[idx].shortstyle.."_bnm.rx3;"
	
	-- kitstring = kitstring.."data/sceneassets/kitcmn/specificshorts_"..db.player[idx].kit.."_0_0_"..db.player[idx].shortstyle.."_bnm.rx3;"
	-- return kitstring
-- end


function GetRMShortModel(idx,lod)
	local short = ""
	
	if (db.player[idx].shortstyle == 0) then
	-- short = short.."data/sceneassets/body/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_"..db.player[idx].kit.."_0_0_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_0_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_0_"..db.player[idx].kitYearDecade.."_"..lod..".rx3;"
	
	-- short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_0_0_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_0_0_"..db.player[idx].tournid.."_"..lod..".rx3;"
	-- short = short.."data/sceneassets/body/specificshorts_0_0_0_"..db.player[idx].kitYearDecade.."_"..lod..".rx3;"
	
	
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].kitType+(db.player[idx].gender*100)).."_"..db.player[idx].tournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].kitType+(db.player[idx].gender*100)).."_"..db.player[idx].defaulttournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].gender*100).."_"..db.player[idx].tournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].gender*100).."_"..db.player[idx].defaulttournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].kitType+(db.player[idx].gender*100)).."_0_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_"..db.player[idx].kit.."_"..(db.player[idx].gender*100).."_0_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_0_"..(db.player[idx].gender*100).."_"..db.player[idx].tournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_0_"..(db.player[idx].gender*100).."_"..db.player[idx].defaulttournid.."_"..lod..".rx3;"
	short = short.."data/sceneassets/body/specificshorts_0_0_"..(db.player[idx].gender*100).."_"..db.player[idx].kitYearDecade.."_"..lod..".rx3;"
	
	short = short.."data/sceneassets/body/specificshorts_"..db.player[idx].playerassetid.."_0_0_0_"..lod..".rx3;"
	end

	return short
end


function GetRMKitOverlay(idx)
	local kitstring = ""
	
	local isfinal = getTournamentFinal(db.player[idx].tournid,db.player[idx].stadiumID,db.player[idx].crowdDistribution)
	
	if (db.player[idx].kitType ~= 5) then
	if (isfinal) then
	
	
	
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+2)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+2)..".png;"
	
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+3)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_"..db.player[idx].defaulttournid.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+3)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].tournid.."_"..(((db.player[idx].gender*10)+3)+db.player[idx].overlayoffset)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+3)..".png;"
	end
	
	
	if (db.player[idx].kitYearDecade > 0) then
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].speckitType*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].speckitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].speckitType*100)+db.player[idx].shirtid).."_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].kitType*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].kitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].kitType*100)+db.player[idx].shirtid).."_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_0_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_"..db.player[idx].defaulttournid.."_"..db.player[idx].classictournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].classictournid.."_"..(((db.player[idx].gender*10)+1)+db.player[idx].overlayoffset)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	end

	
	
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].speckitType*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].speckitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].speckitType*100)+db.player[idx].shirtid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].kitType*1000000)+db.player[idx].playerassetid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].kitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].kitType*100)+db.player[idx].shirtid).."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_0_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_"..db.player[idx].defaulttournid.."_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].tournid.."_"..(((db.player[idx].gender*10)+1)+db.player[idx].overlayoffset)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].tournid.."_"..((db.player[idx].gender*10)+1)..".png;"

	if (db.player[idx].kitYearDecade == -1) then
	
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].speckitType*1000000)+db.player[idx].playerassetid).."_0_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].speckitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_0_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].speckitType*100)+db.player[idx].shirtid).."_0_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_"..db.player[idx].defaulttournid.."_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].speckitType.."_0_"..((db.player[idx].gender*10)+0)..".png;"

	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(300000000+(db.player[idx].kitType*1000000)+db.player[idx].playerassetid).."_0_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(db.player[idx].kitType+100)..db.player[idx].kitNumberTens..db.player[idx].kitNumberUnits.."_0_"..((db.player[idx].gender*10)+0)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..(20000+(db.player[idx].kitType*100)+db.player[idx].shirtid).."_0_"..((db.player[idx].gender*10)+0)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_"..db.player[idx].kitType.."_0_"..((db.player[idx].gender*10)+0)..".png;"
	
	
	
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_0_"..db.player[idx].defaulttournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_"..db.player[idx].kit.."_0_0_"..((db.player[idx].gender*10)+1)..".png;"
	kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].defaulttournid.."_"..(((db.player[idx].gender*10)+1)+db.player[idx].overlayoffset)..".png;"
	--kitstring = kitstring.."data/sceneassets/kitoverlay/kitoverlay_0_0_"..db.player[idx].defaulttournid.."_"..((db.player[idx].gender*10)+1)..".png;"
	
	--kitstring = kitstring.."data/sceneassets/kit/kit_"..db.player[idx].genkit.."_"..db.player[idx].kitType.."_"..db.player[idx].kitYear..".rx3"
	end
	
	end
	

	
	--REFS CLASSIC KITS TRAINING KITS
	--data/sceneassets/kitoverlay/kitoverlay_team_type_tourn_target.png
	--disable for players unless use is found, maybe shirt numbers
	--default tournament
	--ensure blank texture is present
	--allow numbers for classic kits
	
	
	return kitstring
end


-- refereeKitList = {}

-- function setRefereeKits(team,kittype,tournament,opt4,opt5,opt6,opt7,opt8,opt9)

-- if (refereeKitList[team] == nil) then
-- refereeKitList[team] = {}
-- end

-- if (refereeKitList[team][kittype] == nil) then
-- refereeKitList[team][kittype] = {}
-- end

-- if (refereeKitList[team][kittype][tournament] == nil) then
-- refereeKitList[team][kittype][tournament] = {}
-- end

-- if (refereeKitList[team][kittype][tournament][opt4] == nil) then
-- refereeKitList[team][kittype][tournament][opt4] = {}
-- end


-- end


gentexsize = 2048
gentexmip = 9
gentexformat = "eadxt1"

function setGentexSettings(size,mip,formatt)
gentexsize = size
gentexmip = mip
gentexformat = formatt
end

indivKits = false
indivKitsTeam = {}

function enableIndividualKitsGlobal()
indivKits = true
end

function enableIndividualKitsTeam(team,kittype,kityear)
if (indivKitsTeam[team] == nil) then
indivKitsTeam[team] = {}
end

if (indivKitsTeam[team][kittype] == nil) then
indivKitsTeam[team][kittype] = {}
end

if (indivKitsTeam[team][kittype][kityear] == nil) then
indivKitsTeam[team][kittype][kityear] = 1
end
end

function getIndividualKitsTeam(team,kittype,kityear,year)

if (indivKitsTeam[team] ~= nil) then
if (indivKitsTeam[team][kittype] ~= nil) then
if (indivKitsTeam[team][kittype][kityear] ~= nil) then
if (indivKitsTeam[team][kittype][kityear] == 1) then
return true
end
end
end
end

if (year == 0) then
if (indivKitsTeam[team] ~= nil) then
if (indivKitsTeam[team][kittype] ~= nil) then
if (indivKitsTeam[team][kittype][0] ~= nil) then
if (indivKitsTeam[team][kittype][0] == 1) then
return true
end
end
end
end
end


return indivKits
end



function getColourDistance(col1,col2)
lab1 = hexToLab(col1)
lab2 = hexToLab(col2)

value1 = math.sqrt(math.pow((lab1[1]-lab2[1]),2)+math.pow((lab1[2]-lab2[2]),2)+math.pow((lab1[3]-lab2[3]),2))*4.1






r1 = tonumber(string.sub(col1,1,2),16)
g1 = tonumber(string.sub(col1,3,4),16)
b1 = tonumber(string.sub(col1,5,6),16)

r2 = tonumber(string.sub(col2,1,2),16)
g2 = tonumber(string.sub(col2,3,4),16)
b2 = tonumber(string.sub(col2,5,6),16)

value2 = math.sqrt(math.pow((r1-r2),2)+math.pow((g1-g2),2)+math.pow((b1-b2),2))




rmean = ( r1 + r2 ) / 2
r = r1 - r2
g = g1 - g2
b = b1 - b2

value3 = math.sqrt(rshift(((512+rmean)*r*r),8) + (4*g*g) + rshift(((767-rmean)*b*b),8))/1.9


value = value1

if (value2 < value) then
value = value2
end

if (value3 < value) then
value = value3
end


return value
end

function getColourDistanceXXX(col1,col2)
r1 = tonumber(string.sub(col1,1,2),16)
g1 = tonumber(string.sub(col1,3,4),16)
b1 = tonumber(string.sub(col1,5,6),16)

r2 = tonumber(string.sub(col2,1,2),16)
g2 = tonumber(string.sub(col2,3,4),16)
b2 = tonumber(string.sub(col2,5,6),16)

--val = math.sqrt(math.pow((r1-r2),2)+math.pow((g1-g2),2)+math.pow((b1-b2),2))


rmean = ( r1 + r2 ) / 2
r = r1 - r2
g = g1 - g2
b = b1 - b2
--val = math.sqrt((((512+rmean)*r*r)>>8) + (4*g*g) + (((767-rmean)*b*b)>>8))

val = math.sqrt(rshift(((512+rmean)*r*r),8) + (4*g*g) + rshift(((767-rmean)*b*b),8))/2

return val
end

function rshift(x, by)
  return math.floor(x / 2 ^ by)
end



teamKitColoursShirt1 = {}
teamKitColoursShirt2 = {}
teamKitColoursShort = {}
teamKitColoursSock = {}

teamKitColoursTournamentShirt1 = {}
teamKitColoursTournamentShirt2 = {}
teamKitColoursTournamentShort = {}
teamKitColoursTournamentSock = {}

refereeKitColoursTournament = {}

function identifyTeamKitColours(team,kittype,shirt1,shirt2,short,sock)

if (teamKitColoursShirt1[team] == nil) then
teamKitColoursShirt1[team] = {}
teamKitColoursShirt2[team] = {}
teamKitColoursShort[team] = {}
teamKitColoursSock[team] = {}
end


teamKitColoursShirt1[team][kittype] = shirt1
teamKitColoursShirt2[team][kittype] = shirt2
teamKitColoursShort[team][kittype] = short
teamKitColoursSock[team][kittype] = sock

end

function identifyTeamKitColoursTournament(team,kittype,tourn,shirt1,shirt2,short,sock)

if (teamKitColoursTournamentShirt1[team] == nil) then
teamKitColoursTournamentShirt1[team] = {}
teamKitColoursTournamentShirt2[team] = {}
teamKitColoursTournamentShort[team] = {}
teamKitColoursTournamentSock[team] = {}
end

if (teamKitColoursTournamentShirt1[team][kittype] == nil) then
teamKitColoursTournamentShirt1[team][kittype] = {}
teamKitColoursTournamentShirt2[team][kittype] = {}
teamKitColoursTournamentShort[team][kittype] = {}
teamKitColoursTournamentSock[team][kittype] = {}
end

teamKitColoursTournamentShirt1[team][kittype][tourn] = shirt1
teamKitColoursTournamentShirt2[team][kittype][tourn] = shirt2
teamKitColoursTournamentShort[team][kittype][tourn] = short
teamKitColoursTournamentSock[team][kittype][tourn] = sock

end

function identifyRefereeKitColoursTournament(tourn,kit4,kit5,kit6,kit7,kit8,kit9)

if (refereeKitColoursTournament[tourn] == nil) then
refereeKitColoursTournament[tourn] = {}
end

refereeKitColoursTournament[tourn][4] = kit4
refereeKitColoursTournament[tourn][5] = kit5
refereeKitColoursTournament[tourn][6] = kit6
refereeKitColoursTournament[tourn][7] = kit7
refereeKitColoursTournament[tourn][8] = kit8
refereeKitColoursTournament[tourn][9] = kit9

end


function getRefereeKitColours(tourn,home,kittype)

if (refereeKitColoursTournament[tourn] ~= nil) then
if (refereeKitColoursTournament[tourn][kittype] ~= nil) then
return refereeKitColoursTournament[tourn][kittype]
end
end

if (teamTournament[home] ~= nil) then
if (refereeKitColoursTournament[teamTournament[home]] ~= nil) then
if (refereeKitColoursTournament[teamTournament[home]][kittype] ~= nil) then
return refereeKitColoursTournament[teamTournament[home]][kittype]
end
end
end

if (refereeKitColoursTournament[0] ~= nil) then
if (refereeKitColoursTournament[0][kittype] ~= nil) then
return refereeKitColoursTournament[0][kittype]
end
end

return -1
end






function getShirt1Colour(team,kittype,tournament,kityear)

-- local ctournament = (kityear*10000) + tournament

-- if (kityear > 0) then
-- if (teamKitColoursTournamentShirt1[team] ~= nil) then
-- if (teamKitColoursTournamentShirt1[team][kittype] ~= nil) then
-- if (teamKitColoursTournamentShirt1[team][kittype][ctournament] ~= nil) then
-- return teamKitColoursTournamentShirt1[team][kittype][ctournament]
-- end
-- end
-- end
-- end

if (teamKitColoursTournamentShirt1[team] ~= nil) then
if (teamKitColoursTournamentShirt1[team][kittype] ~= nil) then
if (teamKitColoursTournamentShirt1[team][kittype][tournament] ~= nil) then
return teamKitColoursTournamentShirt1[team][kittype][tournament]
end
end
end

if (kityear == 0) then
if (teamKitColoursShirt1[team] ~= nil) then
if (teamKitColoursShirt1[team][kittype] ~= nil) then
return teamKitColoursShirt1[team][kittype]
end
end
end

return -1
end

function getShirt2Colour(team,kittype,tournament,kityear)

if (teamKitColoursTournamentShirt2[team] ~= nil) then
if (teamKitColoursTournamentShirt2[team][kittype] ~= nil) then
if (teamKitColoursTournamentShirt2[team][kittype][tournament] ~= nil) then
return teamKitColoursTournamentShirt2[team][kittype][tournament]
end
end
end

if (kityear == 0) then
if (teamKitColoursShirt2[team] ~= nil) then
if (teamKitColoursShirt2[team][kittype] ~= nil) then
return teamKitColoursShirt2[team][kittype]
end
end
end

return -1
end

function getShortColour(team,kittype,tournament,kityear)

if (teamKitColoursTournamentShort[team] ~= nil) then
if (teamKitColoursTournamentShort[team][kittype] ~= nil) then
if (teamKitColoursTournamentShort[team][kittype][tournament] ~= nil) then
return teamKitColoursTournamentShort[team][kittype][tournament]
end
end
end

if (kityear == 0) then
if (teamKitColoursShort[team] ~= nil) then
if (teamKitColoursShort[team][kittype] ~= nil) then
return teamKitColoursShort[team][kittype]
end
end
end

return -1
end

function getSockColour(team,kittype,tournament,kityear)

if (teamKitColoursTournamentSock[team] ~= nil) then
if (teamKitColoursTournamentSock[team][kittype] ~= nil) then
if (teamKitColoursTournamentSock[team][kittype][tournament] ~= nil) then
return teamKitColoursTournamentSock[team][kittype][tournament]
end
end
end

if (kityear == 0) then
if (teamKitColoursSock[team] ~= nil) then
if (teamKitColoursSock[team][kittype] ~= nil) then
return teamKitColoursSock[team][kittype]
end
end
end

return -1
end


altShorts = {}
altSocks = {}
altShortsSocks = {}


function assignKitAlternates(team,kittype,altshort,altsock,altshortsock)

if (altShorts[team] == nil) then
altShorts[team] = {}
altSocks[team] = {}
altShortsSocks[team] = {}
end

altShorts[team][kittype] = altshort
altSocks[team][kittype] = altsock
altShortsSocks[team][kittype] = altshortsock

end

function getAltShorts(team,kittype,tourn,year)

if (year == 0) then
if (altShorts[team] ~= nil) then
if (altShorts[team][kittype] ~= nil) then
return altShorts[team][kittype]
end
end
end

return -1
end

function getAltSocks(team,kittype,tourn,year)

if (year == 0) then
if (altSocks[team] ~= nil) then
if (altSocks[team][kittype] ~= nil) then
return altSocks[team][kittype]
end
end
end

return -1
end

function getAltShortsSocks(team,kittype,tourn,year)

if (year == 0) then
if (altShortsSocks[team] ~= nil) then
if (altShortsSocks[team][kittype] ~= nil) then
return altShortsSocks[team][kittype]
end
end
end

return -1
end





gkKitOrder = {}
gkKitOrderRand = {}
gkKitOrderTourn = {}
gkKitOrderRandTourn = {}

function assignGKKitPrecedence(team,kittype,randomused,list)

if (gkKitOrder[team] == nil) then
gkKitOrder[team] = {}
gkKitOrderRand[team] = {}
end

gkKitOrder[team][kittype] = list
gkKitOrderRand[team][kittype] = randomused

end

function assignTournamentGKKitPrecedence(team,kittype,tourn,randomused,list)

if (gkKitOrderTourn[team] == nil) then
gkKitOrderTourn[team] = {}
gkKitOrderRandTourn[team] = {}
end

if (gkKitOrderTourn[team][kittype] == nil) then
gkKitOrderTourn[team][kittype] = {}
gkKitOrderRandTourn[team][kittype] = {}
end

gkKitOrderTourn[team][kittype][tourn] = list
gkKitOrderRandTourn[team][kittype][tourn] = randomused

end

function getGKKitPrecedenceList(team,kittype,tourn,year)


if (gkKitOrderTourn[team] ~= nil) then
if (gkKitOrderTourn[team][kittype] ~= nil) then
if (gkKitOrderTourn[team][kittype][tourn] ~= nil) then
return gkKitOrderTourn[team][kittype][tourn]
end
end
end


if (year == 0) then
if (gkKitOrder[team] ~= nil) then
if (gkKitOrder[team][kittype] ~= nil) then
return gkKitOrder[team][kittype]
end
end

if (outfieldasaltgk) then

local order = {2}

--order[#order+1] = 3
--order[#order+1] = 1
--order[#order+1] = 0

if (not (kittype == 3)) then
if (kitNumberColourShortBackup[team] ~= nil) then
if (kitNumberColourShortBackup[team][3] ~= nil) then
order[#order+1] = 3
end
end
end

if (not (kittype == 1)) then
if (kitNumberColourShortBackup[team] ~= nil) then
if (kitNumberColourShortBackup[team][1] ~= nil) then
order[#order+1] = 1
end
end
end

if (not (kittype == 0)) then
if (kitNumberColourShortBackup[team] ~= nil) then
if (kitNumberColourShortBackup[team][0] ~= nil) then
order[#order+1] = 0
end
end
end

return order
end



end

return -1
end

function getGKKitPrecedenceRand(team,kittype,tourn,year)


if (gkKitOrderRandTourn[team] ~= nil) then
if (gkKitOrderRandTourn[team][kittype] ~= nil) then
if (gkKitOrderRandTourn[team][kittype][tourn] ~= nil) then
return gkKitOrderRandTourn[team][kittype][tourn]
end
end
end

if (year == 0) then
if (gkKitOrderRand[team] ~= nil) then
if (gkKitOrderRand[team][kittype] ~= nil) then
return gkKitOrderRand[team][kittype]
end
end
end

return -1
end





function getGKKitColour(team1,team2,team1type,team2type,team1tourn,team2tourn,team1year,team2year,team1origtype,team2origtype,team2gktype)

team1typeshirt = getIndividualKitPart(team1type,1)

team2typeshirt = getIndividualKitPart(team2type,1)
team2typesock = getIndividualKitPart(team2type,3)

team1origtypeshirt = getIndividualKitPart(team1origtype,1)

team2gktypeshirt = getIndividualKitPart(team2gktype,1)



opponentcolour1 = getShirt1Colour(team2,team2typeshirt,team2tourn,team2year)
opponentcolour2 = getShirt2Colour(team2,team2typeshirt,team2tourn,team2year)
opponentcoloursock = getSockColour(team2,team2typesock,team2tourn,team2year)

opponentgkcolour1 = getShirt1Colour(team2,team2gktypeshirt,team2tourn,team2year)
opponentgkcolour2 = getShirt2Colour(team2,team2gktypeshirt,team2tourn,team2year)
--opponentgkcoloursock = getSockColour(team2,team2gktype,team2tourn,team2year)

rchoice1 = -1
rchoice2 = -1

gklist = getGKKitPrecedenceList(team1,team1typeshirt,team1tourn,team1year)
isrand = getGKKitPrecedenceRand(team1,team1typeshirt,team1tourn,team1year)

if (gklist == -1) then
gklist = getGKKitPrecedenceList(team1,team1origtypeshirt,team1tourn,team1year)
isrand = getGKKitPrecedenceRand(team1,team1origtypeshirt,team1tourn,team1year)
end

if (gklist ~= -1) then
gklistsize = #gklist

if (gklistsize == 1) then
return gklist[1]
end

gkkitfirst = 1


if (isrand == 1) then
gkkitfirst = math.random(gklistsize)
end

gkitcount = gkkitfirst

doloop = true

while (doloop) do
test = true
test2 = true
test3 = true

gkcolour1 = getShirt1Colour(team1,gklist[gkitcount],team1tourn,team1year)
gkcolour2 = getShirt2Colour(team1,gklist[gkitcount],team1tourn,team1year)
gkcoloursock = getSockColour(team1,gklist[gkitcount],team1tourn,team1year)

if (gkcolour1 ~= -1) then
if (opponentcolour1 ~= -1) then
if (getColourDistance(opponentcolour1,gkcolour1) < gkoutshirttol) then
test = false
end
end
if (opponentcolour2 ~= -1) then
if (getColourDistance(opponentcolour2,gkcolour1) < gkoutshirttol) then
test = false
end
end
end
if (gkcolour2 ~= -1) then
if (opponentcolour1 ~= -1) then
if (getColourDistance(opponentcolour1,gkcolour2) < gkoutshirttol) then
test = false
end
end
if (opponentcolour2 ~= -1) then
if (getColourDistance(opponentcolour2,gkcolour2) < gkoutshirttol) then
test = false
end
end
end

if (gkcolour1 ~= -1) then
if (opponentgkcolour1 ~= -1) then
if (getColourDistance(opponentgkcolour1,gkcolour1) < gkgkshirttol) then
test2 = false
end
end
if (opponentgkcolour2 ~= -1) then
if (getColourDistance(opponentgkcolour2,gkcolour1) < gkgkshirttol) then
test2 = false
end
end
end
if (gkcolour2 ~= -1) then
if (opponentgkcolour1 ~= -1) then
if (getColourDistance(opponentgkcolour1,gkcolour2) < gkgkshirttol) then
test2 = false
end
end
if (opponentgkcolour2 ~= -1) then
if (getColourDistance(opponentgkcolour2,gkcolour2) < gkgkshirttol) then
test2 = false
end
end
end

if (gkcoloursock ~= -1) then
if (opponentcoloursock ~= -1) then
if (getColourDistance(opponentcoloursock,gkcoloursock) < gkoutsocktol) then
test3 = false
end
end
end

if ((test and test2) and test3) then
return gklist[gkitcount]
end

if ((test and (rchoice1 == -1)) and test2) then
rchoice1 = gklist[gkitcount]
end

if (test and (rchoice2 == -1)) then
rchoice2 = gklist[gkitcount]
end

gkitcount = gkitcount + 1
if (gkitcount > gklistsize) then
gkitcount = 1
end


if (gkitcount == gkkitfirst) then
doloop = false
end

end
end
	

if (rchoice1 ~= -1) then
return rchoice1
end

if (rchoice2 ~= -1) then
return rchoice2
end

if (gklist ~= -1) then
return gklist[1]
end


return -1
end






function getRefereeKitColour(team1,team2,team1type,team2type,team1tourn,team2tourn,team1year,team2year,refkit,tourn,team1gktype,team2gktype)

rrchoice1 = -1

homecolour1 = getShirt1Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
homecolour2 = getShirt2Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
awaycolour1 = getShirt1Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)
awaycolour2 = getShirt2Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)

homegkcolour1 = getShirt1Colour(team1,getIndividualKitPart(team1gktype,1),team1tourn,team1year)
homegkcolour2 = getShirt2Colour(team1,getIndividualKitPart(team1gktype,1),team1tourn,team1year)
awaygkcolour1 = getShirt1Colour(team2,getIndividualKitPart(team2gktype,1),team2tourn,team2year)
awaygkcolour2 = getShirt2Colour(team2,getIndividualKitPart(team2gktype,1),team2tourn,team2year)

rkit = refkit%10

if (rkit < 4) then
rkit = 4
end

rkitcount = rkit

doloop = true

while (doloop) do
test = true
test2 = true

refereecolour = getRefereeKitColours(tourn,team1,rkitcount)

-- if (refereecolour ~= -1) then
-- useGlobalTournamentGraphics(980)
-- end

if (refereecolour ~= -1) then
if (homecolour1 ~= -1) then
if (getColourDistance(homecolour1,refereecolour) < refoutshirttol) then
test = false
end
end
if (homecolour2 ~= -1) then
if (getColourDistance(homecolour2,refereecolour) < refoutshirttol) then
test = false
end
end
if (awaycolour1 ~= -1) then
if (getColourDistance(awaycolour1,refereecolour) < refoutshirttol) then
test = false
end
end
if (awaycolour2 ~= -1) then
if (getColourDistance(awaycolour2,refereecolour) < refoutshirttol) then
test = false
end
end
end

if (refereecolour ~= -1) then
if (homegkcolour1 ~= -1) then
if (getColourDistance(homegkcolour1,refereecolour) < refgkshirttol) then
test2 = false
end
end
if (homegkcolour2 ~= -1) then
if (getColourDistance(homegkcolour2,refereecolour) < refgkshirttol) then
test2 = false
end
end
if (awaygkcolour1 ~= -1) then
if (getColourDistance(awaygkcolour1,refereecolour) < refgkshirttol) then
test2 = false
end
end
if (awaygkcolour2 ~= -1) then
if (getColourDistance(awaygkcolour2,refereecolour) < refgkshirttol) then
test2 = false
end
end
end

if (test and test2) then
return rkitcount + 6000
--doloop = false
end

if (test and (rrchoice1 == -1)) then
rrchoice1 = rkitcount + 6000
end

rkitcount = rkitcount + 1
if (rkitcount > 9) then
rkitcount = 4
end

if (rkitcount == rkit) then
doloop = false
end

end

return rrchoice1
end



altKitParts = {}
altKitPartsOption = {}
altKitPartsTourn = {}
altKitPartsOptionTourn = {}

function assignKitAlternateParts(team,kittype,altkittype,option)

if (altKitParts[team] == nil) then
altKitParts[team] = {}
altKitPartsOption[team] = {}
end

altKitParts[team][kittype] = altkittype
altKitPartsOption[team][kittype] = option
end

function assignTournamentKitAlternateParts(team,kittype,tourn,altkittype,option)

if (altKitPartsTourn[team] == nil) then
altKitPartsTourn[team] = {}
altKitPartsOptionTourn[team] = {}
end

if (altKitPartsTourn[team][kittype] == nil) then
altKitPartsTourn[team][kittype] = {}
altKitPartsOptionTourn[team][kittype] = {}
end

altKitPartsTourn[team][kittype][tourn] = altkittype
altKitPartsOptionTourn[team][kittype][tourn] = option
end

function getKitAlternateParts(team,kittype,tourn,year)

if (altKitPartsTourn[team] ~= nil) then
if (altKitPartsTourn[team][kittype] ~= nil) then
if (altKitPartsTourn[team][kittype][tourn] ~= nil) then
return altKitPartsTourn[team][kittype][tourn]
end
end
end

if (year == 0) then
if (altKitParts[team] ~= nil) then
if (altKitParts[team][kittype] ~= nil) then
return altKitParts[team][kittype]
end
end
end

return -1
end

function getKitAlternatePartsOption(team,kittype,tourn,year)

if (altKitPartsOptionTourn[team] ~= nil) then
if (altKitPartsOptionTourn[team][kittype] ~= nil) then
if (altKitPartsOptionTourn[team][kittype][tourn] ~= nil) then
return altKitPartsOptionTourn[team][kittype][tourn]
end
end
end

if (year == 0) then
if (altKitPartsOption[team] ~= nil) then
if (altKitPartsOption[team][kittype] ~= nil) then
return altKitPartsOption[team][kittype]
end
end
end

return -1
end



globalAltShortOutfieldOption = false
globalAltSockOutfieldOption = false

globalAltShortGKOption = false
globalAltSockGKOption = false

function setGlobalKitAlternateOptions(outoption,gkoption)

if (outoption == 0) then
globalAltShortOutfieldOption = false
globalAltSockOutfieldOption = false
end

if (outoption == 1) then
globalAltShortOutfieldOption = true
globalAltSockOutfieldOption = false
end

if (outoption == 2) then
globalAltShortOutfieldOption = false
globalAltSockOutfieldOption = true

end

if (outoption == 3) then
globalAltShortOutfieldOption = true
globalAltSockOutfieldOption = true
end


if (gkoption == 0) then
globalAltShortGKOption = false
globalAltSockGKOption = false
end

if (gkoption == 1) then
globalAltShortGKOption = true
globalAltSockGKOption = false
end

if (gkoption == 2) then
globalAltShortGKOption = false
globalAltSockGKOption = true
end

if (gkoption == 3) then
globalAltShortGKOption = true
globalAltSockGKOption = true
end

end




function getAltKitColour(team1,team2,team1type,team2type,team1tourn,team2tourn,team1year,team2year,team1outfieldtype)

team1typeshirt = getIndividualKitPart(team1type,1)
team1typeshort = getIndividualKitPart(team1type,2)
team1typesock = getIndividualKitPart(team1type,3)

--team2typeshirt = getIndividualKitPart(team2type,1)
team2typeshort = getIndividualKitPart(team2type,2)
team2typesock = getIndividualKitPart(team2type,3)

team1outfieldtypeshort = getIndividualKitPart(team1outfieldtype,2)
team1outfieldtypesock = getIndividualKitPart(team1outfieldtype,3)


altShortsType = getAltShorts(team1,team1typeshirt,team1tourn,team1year)
altSocksType = getAltSocks(team1,team1typeshirt,team1tourn,team1year)
altShortsSocksType = getAltShortsSocks(team1,team1typeshirt,team1tourn,team1year)

altPartsTypeShorts = getIndividualKitPart(getKitAlternateParts(team1,team1type,team1tourn,team1year),2)
altPartsTypeSocks = getIndividualKitPart(getKitAlternateParts(team1,team1type,team1tourn,team1year),3)

if (altPartsTypeShorts == -1) then
altPartsTypeShorts = getIndividualKitPart(getKitAlternateParts(team1,team1typeshirt,team1tourn,team1year),2)
end
if (altPartsTypeSocks == -1) then
altPartsTypeSocks = getIndividualKitPart(getKitAlternateParts(team1,team1typeshirt,team1tourn,team1year),3)
end

altPartsTypeOption = getKitAlternatePartsOption(team1,team1typeshirt,team1tourn,team1year)

if (team1year == 0) then

if (globalAltShortOutfieldOption) then
if (team1outfieldtypesock == -1) then
if (altPartsTypeShorts == -1) then
if (team1typeshirt == 0) then
altPartsTypeShorts = 1
end
if (team1typeshirt == 1) then
altPartsTypeShorts = 0
end
if (team1typeshirt == 3) then
altPartsTypeShorts = 0
end
end
end
end

if (globalAltSockOutfieldOption) then
if (team1outfieldtypesock == -1) then
if (altPartsTypeSocks == -1) then
if (team1typeshirt == 0) then
altPartsTypeSocks = 1
end
if (team1typeshirt == 1) then
altPartsTypeSocks = 0
end
if (team1typeshirt == 3) then
altPartsTypeSocks = 0
end
end
end
end

if (globalAltShortGKOption) then
if (team1outfieldtypesock ~= -1) then
if (altPartsTypeShorts == -1) then
altPartsTypeShorts = team1outfieldtypeshort
end
end
end

if (globalAltSockGKOption) then
if (team1outfieldtypesock ~= -1) then
if (altPartsTypeSocks == -1) then
altPartsTypeSocks = team1outfieldtypesock
end
end
end

end



if (altPartsTypeOption == 0) then
altPartsTypeShorts = -1
altPartsTypeSocks = -1
end

if (altPartsTypeOption == 1) then
altPartsTypeSocks = -1
end

if (altPartsTypeOption == 2) then
altPartsTypeShorts = -1
end


if (altPartsTypeOption == 4) then
altPartsTypeShorts = team1outfieldtypeshort
altPartsTypeSocks = -1
end

if (altPartsTypeOption == 5) then
altPartsTypeShorts = -1
altPartsTypeSocks = team1outfieldtypesock
end

if (altPartsTypeOption == 6) then
altPartsTypeShorts = team1outfieldtypeshort
altPartsTypeSocks = team1outfieldtypesock
end

-- if (altPartsTypeOption == 1) then
-- altPartsTypeShorts = -1
-- altPartsTypeSocks = -1
-- end



testshort = true
testsock = true

testshortalt = true
testsockalt = true

opponentcolourshort = getShortColour(team2,team2typeshort,team2tourn,team2year)
opponentcoloursock = getSockColour(team2,team2typesock,team2tourn,team2year)

teamcolourshort = getShortColour(team1,team1typeshort,team1tourn,team1year)
teamcoloursock = getSockColour(team1,team1typesock,team1tourn,team1year)

teamcolourshortalt = getShortColour(team1,altPartsTypeShorts,team1tourn,team1year)
teamcoloursockalt = getSockColour(team1,altPartsTypeSocks,team1tourn,team1year)

if (teamcolourshort ~= -1) then
if (opponentcolourshort ~= -1) then
if (getColourDistance(opponentcolourshort,teamcolourshort) < outoutshorttol) then
testshort = false
end
end
end

if (teamcoloursock ~= -1) then
if (opponentcoloursock ~= -1) then
if (getColourDistance(opponentcoloursock,teamcoloursock) < outoutsocktol) then
testsock = false
end
end
end




if (teamcolourshortalt ~= -1) then
if (opponentcolourshort ~= -1) then
if (getColourDistance(opponentcolourshort,teamcolourshortalt) < outoutshorttol) then
testshortalt = false
end
end
end

if (teamcoloursockalt ~= -1) then
if (opponentcoloursock ~= -1) then
if (getColourDistance(opponentcoloursock,teamcoloursockalt) < outoutsocktol) then
testsockalt = false
end
end
end


if ((not testshort) and (not testshortalt)) then
if (getColourDistance(opponentcolourshort,teamcolourshortalt) - getColourDistance(opponentcolourshort,teamcolourshort) > 20) then
testshortalt = true
end
end

if ((not testsock) and (not testsockalt)) then
if (getColourDistance(opponentcoloursock,teamcoloursockalt) - getColourDistance(opponentcoloursock,teamcoloursock) > 20) then
testsockalt = true
end
end


if (altPartsTypeOption == 7) then
testshort = false
testsock = true
testshortalt = true
testsockalt = true
altPartsTypeShorts = team1outfieldtypeshort
altPartsTypeSocks = team1outfieldtypesock
end

if (altPartsTypeOption == 8) then
testshort = true
testsock = false
testshortalt = true
testsockalt = true
altPartsTypeShorts = team1outfieldtypeshort
altPartsTypeSocks = team1outfieldtypesock
end

if (altPartsTypeOption == 9) then
testshort = false
testsock = false
testshortalt = true
testsockalt = true
altPartsTypeShorts = team1outfieldtypeshort
altPartsTypeSocks = team1outfieldtypesock
end




-- if (testshort and testsock) then
-- return -1
-- end

if ((not testshort) and testsock) then
if (altShortsType ~= -1) then
return altShortsType
else
if ((altPartsTypeShorts ~= -1) and testshortalt) then
return 4000000 + (team1typeshirt * 10000) + (altPartsTypeShorts * 100) + team1typesock
end
end
end


if (testshort and (not testsock)) then
if (altSocksType ~= -1) then
return altSocksType
else
if ((altPartsTypeSocks ~= -1) and testsockalt) then
return 4000000 + (team1typeshirt * 10000) + (team1typeshort * 100) + altPartsTypeSocks
end
end
end


if ((not testshort) and (not testsock)) then
if (altShortsSocksType ~= -1) then
return altShortsSocksType
else

if (((altPartsTypeShorts ~= -1) and (altPartsTypeSocks ~= -1)) and (testshortalt and testsockalt)) then
return 4000000 + (team1typeshirt * 10000) + (altPartsTypeShorts * 100) + altPartsTypeSocks
end

if ((altPartsTypeShorts ~= -1) and testshortalt) then
return 4000000 + (team1typeshirt * 10000) + (altPartsTypeShorts * 100) + team1typesock
end


if ((altPartsTypeSocks ~= -1) and testsockalt) then
return 4000000 + (team1typeshirt * 10000) + (team1typeshort * 100) + altPartsTypeSocks
end

end
end




return team1type
end




function getAltKit(team1,team2,team1type,team2type,team1tourn,team2tourn,team1year,team2year)

altkittypenew = getAlternateKitFile(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)

if (altkittypenew ~= -1) then

homecolour1 = getShirt1Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
homecolour2 = getShirt2Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
awaycolour1 = getShirt1Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)
awaycolour2 = getShirt2Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)

homecolouralt1 = getShirt1Colour(team1,getIndividualKitPart(altkittypenew,1),team1tourn,team1year)
homecolouralt2 = getShirt2Colour(team1,getIndividualKitPart(altkittypenew,1),team1tourn,team1year)

test = true
test2 = true

if (awaycolour1 ~= -1) then
if (homecolour1 ~= -1) then
if (getColourDistance(homecolour1,awaycolour1) < refoutshirttol) then
test = false
end
end
if (homecolour2 ~= -1) then
if (getColourDistance(homecolour2,awaycolour1) < refoutshirttol) then
test = false
end
end
end

if (awaycolour2 ~= -1) then
if (homecolour1 ~= -1) then
if (getColourDistance(homecolour1,awaycolour2) < refoutshirttol) then
test = false
end
end
if (homecolour2 ~= -1) then
if (getColourDistance(homecolour2,awaycolour2) < refoutshirttol) then
test = false
end
end
end

if (awaycolour1 ~= -1) then
if (homecolouralt1 ~= -1) then
if (getColourDistance(homecolouralt1,awaycolour1) < refoutshirttol) then
test2 = false
end
end
if (homecolouralt2 ~= -1) then
if (getColourDistance(homecolouralt2,awaycolour1) < refoutshirttol) then
test2 = false
end
end
end

if (awaycolour2 ~= -1) then
if (homecolouralt1 ~= -1) then
if (getColourDistance(homecolouralt1,awaycolour2) < refoutshirttol) then
test2 = false
end
end
if (homecolouralt2 ~= -1) then
if (getColourDistance(homecolouralt2,awaycolour2) < refoutshirttol) then
test2 = false
end
end
end

if (not test and test2) then
return altkittypenew
end

end

return team1type
end



altKitFile = {}
altKitFileTourn = {}

function assignAlternateKit(team,kittype,new)

if (altKitFile[team] == nil) then
altKitFile[team] = {}
end

altKitFile[team][kittype] = new

end

function assignTournamentAlternateKit(team,kittype,tourn,new)

if (altKitFileTourn[team] == nil) then
altKitFileTourn[team] = {}
end

if (altKitFileTourn[team][kittype] == nil) then
altKitFileTourn[team][kittype] = {}
end

altKitFileTourn[team][kittype][tourn] = new

end

function getAlternateKitFile(team,kittype,tourn,year)

if (altKitFileTourn[team] ~= nil) then
if (altKitFileTourn[team][kittype] ~= nil) then
if (altKitFileTourn[team][kittype][tourn] ~= nil) then
return altKitFileTourn[team][kittype][tourn]
end
end
end


if (year == 0) then
if (altKitFile[team] ~= nil) then
if (altKitFile[team][kittype] ~= nil) then
return altKitFile[team][kittype]
end
end
end

return -1
end




outoutshorttol = 100
outoutsocktol = 100
gkoutshirttol = 100
gkoutsocktol = 100
gkgkshirttol = 100
refoutshirttol = 100
refgkshirttol = 100


function setOutfieldOutfieldClashThreshold(short,sock)
outoutshorttol = short
outoutsocktol = sock
end

function setOutfieldGKClashThreshold(shirt,sock)
gkoutshirttol = shirt
gkoutsocktol = sock
end

function setGKGKClashThreshold(shirt)
gkgkshirttol = shirt
end

function setOutfieldRefereeClashThreshold(shirt)
refoutshirttol = shirt
end

function setGKRefereeClashThreshold(shirt)
refgkshirttol = shirt
end


globalundershort = -1


function useGlobalUndershorts(option)
globalundershort = option
end



function getIndividualKitPart(number,option)

if (number >= 4000000) then

local sock = number%100

if (option == 3) then
return sock
end

local short = (number-sock)%10000 / 100

if (option == 2) then
return short
end

return (number-(short*100)-sock)%1000000 / 10000
end

return number
end


classicGKMode = false

function enableGenericClassicGKKits()
classicGKMode = true
end

kitsetactiveid = {}


function enableSwapTeamKitSet(id)
kitsetactiveid[id] = 1
end


fourthofficialdry = 0
fourthofficialwet = 0
fourthofficialdrywin = 0
fourthofficialwetwin = 0
fourthofficialsnow = 0


function setFourthOfficialKitType(dry,wet,drywin,wetwin,snow)
fourthofficialdry = dry
fourthofficialwet = wet
fourthofficialdrywin = drywin
fourthofficialwetwin = wetwin
fourthofficialsnow = snow
end

function getFourthOfficialKitType(weather,climate)

if (weather == 2) then
return fourthofficialsnow
end

if ((climate == 1) and (weather == 1)) then
return fourthofficialwetwin
end

if (climate == 1) then
return fourthofficialdrywin
end

if ((climate == 0) and (weather == 1)) then
return fourthofficialwet
end

return fourthofficialdry
end




function GetRMArmbandModel(idx,lod)
	local model = ""
	
	if (lod ~= 2) then
	model = model.."data/sceneassets/body/jersey_"..(lod).."_"..db.player[idx].jerseyCollarType.."_"..db.player[idx].jerseySleeveLength.."_"..db.player[idx].jerseyArmBandCustom.."_"..db.player[idx].jerseyTucked.."_"..db.player[idx].jerseyfit.."_"..db.player[idx].gender..".rx3;"
	else
	model = model.."data/sceneassets/body/jersey_"..(lod).."_"..db.player[idx].jerseySleeveLength.."_"..db.player[idx].jerseyArmBandCustom.."_"..db.player[idx].jerseyTucked.."_"..db.player[idx].gender..".rx3;"
	end

	return model
end

customArmband = {}

function assignArmbandModel(player,model)
customArmband[player] = model
end

function getArmbandModel(player,model)

if (customArmband[player] ~= nil) then
return customArmband[player]
end

return model
end


kitMenuClashing = true

function disableKitSelectionMenuKitClashPreview()
kitMenuClashing = false
end






teamBibColours = {}
teamBibColoursTournament = {}

genericBibColours = {}
genericBibColoursTournament = {}

function identifyTeamBibColour(team,bibtype,colour)

if (teamBibColours[team] == nil) then
teamBibColours[team] = {}
end

teamBibColours[team][bibtype] = colour

end


function identifyTeamBibColourTournament(team,bibtype,tourn,colour)

if (teamBibColoursTournament[team] == nil) then
teamBibColoursTournament[team] = {}
end

if (teamBibColoursTournament[team][bibtype] == nil) then
teamBibColoursTournament[team][bibtype] = {}
end

teamBibColoursTournament[team][bibtype][tourn] = colour

end

function identifyGenericBibColour(bibtype,colour)

genericBibColours[bibtype] = colour

end


function identifyBibColourTournament(bibtype,tourn,colour)


if (genericBibColoursTournament[bibtype] == nil) then
genericBibColoursTournament[bibtype] = {}
end

genericBibColoursTournament[bibtype][tourn] = colour

end


function getBibColour(team,bibtype,tourn)

if (teamBibColoursTournament[team] ~= nil) then
if (teamBibColoursTournament[team][bibtype] ~= nil) then
if (teamBibColoursTournament[team][bibtype][tourn] ~= nil) then
return teamBibColoursTournament[team][bibtype][tourn]
end
end
end

if (genericBibColoursTournament[bibtype] ~= nil) then
if (genericBibColoursTournament[bibtype][tourn] ~= nil) then
return genericBibColoursTournament[bibtype][tourn]
end
end

if (teamBibColours[team] ~= nil) then
if (teamBibColours[team][bibtype] ~= nil) then
return teamBibColours[team][bibtype]
end
end

if (genericBibColours[bibtype] ~= nil) then
return genericBibColours[bibtype]
end

return -1
end







bibOrderTeam = {}
bibOrderRandTeam = {}
bibOrderTourn = {}
bibOrderRandTourn = {}
bibOrderTeamTourn = {}
bibOrderRandTeamTourn = {}

bibOrderGeneric = -1
bibOrderRandGeneric = -1

function assignTeamBibPrecedence(team,bibtype,randomused,list)

if (bibOrderTeam[team] == nil) then
bibOrderTeam[team] = {}
bibOrderRandTeam[team] = {}
end

bibOrderTeam[team][bibtype] = list
bibOrderRandTeam[team][bibtype] = randomused

end

function assignTeamTournamentBibPrecedence(team,bibtype,tourn,randomused,list)

if (bibOrderTourn[team] == nil) then
bibOrderTourn[team] = {}
bibOrderRandTourn[team] = {}
end

if (bibOrderTourn[team][bibtype] == nil) then
bibOrderTourn[team][bibtype] = {}
bibOrderRandTourn[team][bibtype] = {}
end

bibOrderTourn[team][bibtype][tourn] = list
bibOrderRandTourn[team][bibtype][tourn] = randomused

end

function assignTournamentBibPrecedence(tourn,randomused,list)

bibOrderTourn[tourn] = list
bibOrderRandTourn[tourn] = randomused

end

function getBibPrecedenceList(team,bibtype,tourn,year)


if (bibOrderTeamTourn[team] ~= nil) then
if (bibOrderTeamTourn[team][bibtype] ~= nil) then
if (bibOrderTeamTourn[team][bibtype][tourn] ~= nil) then
return bibOrderTeamTourn[team][bibtype][tourn]
end
end
end

if (bibOrderTeamTourn[team] ~= nil) then
if (bibOrderTeamTourn[team][0] ~= nil) then
if (bibOrderTeamTourn[team][0][tourn] ~= nil) then
return bibOrderTeamTourn[team][0][tourn]
end
end
end


if (bibOrderTourn[tourn] ~= nil) then
return bibOrderTourn[tourn]
end


if (year == 0) then
if (bibOrderTeam[team] ~= nil) then
if (bibOrderTeam[team][bibtype] ~= nil) then
return bibOrderTeam[team][bibtype]
end
end
end

if (year == 0) then
if (bibOrderTeam[team] ~= nil) then
if (bibOrderTeam[team][0] ~= nil) then
return bibOrderTeam[team][0]
end
end
end

if (bibOrderGeneric ~= -1) then
return bibOrderGeneric
end

return -1
end

function assignGenericBibPrecedence(randomused,list)

bibOrderGeneric = list
bibOrderRandGeneric = randomused

end

function getBibPrecedenceRand(team,bibtype,tourn,year)


if (bibOrderRandTeamTourn[team] ~= nil) then
if (bibOrderRandTeamTourn[team][bibtype] ~= nil) then
if (bibOrderRandTeamTourn[team][bibtype][tourn] ~= nil) then
return bibOrderRandTeamTourn[team][bibtype][tourn]
end
end
end

if (bibOrderRandTeamTourn[team] ~= nil) then
if (bibOrderRandTeamTourn[team][0] ~= nil) then
if (bibOrderRandTeamTourn[team][0][tourn] ~= nil) then
return bibOrderRandTeamTourn[team][0][tourn]
end
end
end

if (bibOrderRandTourn[tourn] ~= nil) then
return bibOrderRandTourn[tourn]
end

if (bibOrderRandTeam[team] ~= nil) then
if (bibOrderRandTeam[team][bibtype] ~= nil) then
return bibOrderRandTeam[team][bibtype]
end
end

if (bibOrderRandTeam[team] ~= nil) then
if (bibOrderRandTeam[team][0] ~= nil) then
return bibOrderRandTeam[team][0]
end
end

if (bibOrderRandGeneric ~= nil) then
return bibOrderRandGeneric
end

return 0
end





function getBibColourType(team1,team2,team1type,team2type,team1tourn,team2tourn,team1year,team2year,tourn,team1gktype,team2gktype,refkittype,refkittourn,hometeam,otherbib)

rrchoice1 = -1
rrchoice2 = -1
rrchoice3 = -1

homecolour1 = getShirt1Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
homecolour2 = getShirt2Colour(team1,getIndividualKitPart(team1type,1),team1tourn,team1year)
awaycolour1 = getShirt1Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)
awaycolour2 = getShirt2Colour(team2,getIndividualKitPart(team2type,1),team2tourn,team2year)

homegkcolour1 = getShirt1Colour(team1,getIndividualKitPart(team1gktype,1),team1tourn,team1year)
homegkcolour2 = getShirt2Colour(team1,getIndividualKitPart(team1gktype,1),team1tourn,team1year)
awaygkcolour1 = getShirt1Colour(team2,getIndividualKitPart(team2gktype,1),team2tourn,team2year)
awaygkcolour2 = getShirt2Colour(team2,getIndividualKitPart(team2gktype,1),team2tourn,team2year)

refereecolour = getRefereeKitColours(refkittourn,hometeam,(refkittype-6000))

otherbibcolour = getBibColour(team2,otherbib,tourn)

-- refereecolour2 = getRefereeKitColours(tourn,team1,refkittype)
-- if (ishome == 2) then
-- refereecolour2 = getRefereeKitColours(tourn,team2,refkittype)
-- end


--gklist = getGKKitPrecedenceList(team1,team1typeshirt,team1tourn,team1year)
--isrand = getGKKitPrecedenceRand(team1,team1typeshirt,team1tourn,team1year)

--biblist = getBibPrecedenceList(team,bibtype,tourn,year)
biblist = getBibPrecedenceList(team1,team1type,tourn,year)
isrand = getBibPrecedenceRand(team1,team1type,tourn,year)

-- if (biblist == -1) then
-- biblist = getBibPrecedenceList(team1,0,tourn,year)
-- isrand = getBibPrecedenceRand(team1,0,tourn,year)
-- end

--getBibPrecedenceRand(team,bibtype,tourn,year)


if (biblist ~= -1) then
biblistsize = #biblist

if (biblistsize == 1) then
return biblist[1]
end

bibfirst = 1


if (isrand == 1) then
bibfirst = math.random(biblistsize)
end

bibcount = bibfirst













doloop = true

while (doloop) do
test = true
test2 = true
test3 = true
test4 = true

bibcolour = getBibColour(team1,biblist[bibcount],tourn)

if (bibcolour ~= -1) then
if (homecolour1 ~= -1) then
if (getColourDistance(homecolour1,bibcolour) < refoutshirttol) then
test = false
end
end
if (homecolour2 ~= -1) then
if (getColourDistance(homecolour2,bibcolour) < refoutshirttol) then
test = false
end
end
if (awaycolour1 ~= -1) then
if (getColourDistance(awaycolour1,bibcolour) < refoutshirttol) then
test = false
end
end
if (awaycolour2 ~= -1) then
if (getColourDistance(awaycolour2,bibcolour) < refoutshirttol) then
test = false
end
end
end

if (bibcolour ~= -1) then
if (homegkcolour1 ~= -1) then
if (getColourDistance(homegkcolour1,bibcolour) < refgkshirttol) then
test2 = false
end
end
if (homegkcolour2 ~= -1) then
if (getColourDistance(homegkcolour2,bibcolour) < refgkshirttol) then
test2 = false
end
end
if (awaygkcolour1 ~= -1) then
if (getColourDistance(awaygkcolour1,bibcolour) < refgkshirttol) then
test2 = false
end
end
if (awaygkcolour2 ~= -1) then
if (getColourDistance(awaygkcolour2,bibcolour) < refgkshirttol) then
test2 = false
end
end
end




if (bibcolour ~= -1) then
if (otherbibcolour ~= -1) then
if (getColourDistance(otherbibcolour,bibcolour) < refgkshirttol) then
test3 = false
end
end
end


if (bibcolour ~= -1) then
if (refereecolour ~= -1) then
if (getColourDistance(refereecolour,bibcolour) < refgkshirttol) then
test4 = false
end
end
end




if ((test and test2) and (test3 and test4)) then
return biblist[bibcount]
--doloop = false
end


if (((test and test2) and test3) and (rrchoice1 == -1)) then
rrchoice1 = biblist[bibcount]
end

if ((test and test2) and (rrchoice2 == -1)) then
rrchoice2 = biblist[bibcount]
end

if (test and (rrchoice3 == -1)) then
rrchoice3 = biblist[bibcount]
end


bibcount = bibcount + 1
if (bibcount > biblistsize) then
bibcount = 1
end

if (bibcount == bibfirst) then
doloop = false
end

end

end

if (rrchoice1 ~= -1) then
return rrchoice1
end

if (rrchoice2 ~= -1) then
return rrchoice2
end

if (rrchoice3 ~= -1) then
return rrchoice3
end

return -1
end





overlayOffsetTeam = {}

function setTeamKitOverlayVarient(team,offset)

overlayOffsetTeam[team] = offset

end

function getKitOverlayVarient(team)

if (overlayOffsetTeam[team] ~= nil) then
return overlayOffsetTeam[team]
end

return 0
end





genPlayerHairColour = {}

function setPlayerGenericHairColour(player,col)

genPlayerHairColour[player] = hex(col)

end

function getGenericHairColour(player,col)

if (genPlayerHairColour[player] ~= nil) then
return genPlayerHairColour[player]
end

return col
end


forceFemale = false

function setAllPlayersAsFemale()

forceFemale = true

end


enableEAFemaleRefereeKits = true


function disableEAFemaleRefereeKits()
enableEAFemaleRefereeKits = false
end


outfieldasaltgk = false

function globalOutfieldAsAltGK()
outfieldasaltgk = true
end








function hexToLab(col1)

colred = tonumber(string.sub(col1,1,2),16)
colgreen = tonumber(string.sub(col1,3,4),16)
colblue = tonumber(string.sub(col1,5,6),16)
 

col_red = colred/255
col_green = colgreen/255
col_blue = colblue/255
 
if (col_red>0.04045) then
     col_red = (col_red+0.055)/1.055
     col_red = col_red^2.4
else
     col_red = col_red/12.92
end
if (col_green>0.04045) then
     col_green = (col_green+0.055)/1.055
     col_green = col_green^2.4    
else
     col_green = col_green/12.92
end
if (col_blue>0.04045) then
     col_blue = (col_blue+0.055)/1.055
     col_blue = col_blue^2.4 
else
     col_blue = col_blue/12.92
end
 
col_red = col_red*100
col_green = col_green*100
col_blue = col_blue*100
 

col_x = (col_red * 0.4124) + (col_green * 0.3576) + (col_blue * 0.1805)
col_y = (col_red * 0.2126) + (col_green * 0.7152) + (col_blue * 0.0722)
col_z = (col_red * 0.0193) + (col_green * 0.1192) + (col_blue * 0.9505)
 
 
col_x = col_x/95.047
col_y = col_y/100
col_z = col_z/108.883
 

if (col_x>0.008856) then
     col_x = col_x^(1/3)
else
     col_x = ((7.787*col_x) + 16)/116
end
if (col_y>0.008856) then
     col_y = col_y^(1/3)
else
     col_y = ((7.787*col_y) + 16)/116
end
if (col_z>0.008856) then
     col_z = col_z^(1/3)
else
     col_z = ((7.787*col_z) + 16)/116
end
 
col_l= (116*col_y)-16
col_a= 500*(col_x-col_y)
col_b= 200*(col_y-col_z)
 
lab = {}
lab[1] = col_l
lab[2] = col_a
lab[3] = col_b

return lab
end




kitNameColourTournamentGeneric = {}

function assignTournamentKitNameColour(tourn,colour,colourstring)

if (kitNameColourTournamentGeneric[tourn] == nil) then
kitNameColourTournamentGeneric[tourn] = {}
end

kitNameColourTournamentGeneric[tourn][colour] = hex(colourstring)

end


fourthOfficialCollar = {}

function assignFourthOfficialCollar(tourn,colar)

fourthOfficialCollar[tourn] = colar

end


function getFourthOfficialCollar(tourn,dtourn,colar)

if (fourthOfficialCollar[tourn] ~= nil) then
return fourthOfficialCollar[tourn]
end

if (fourthOfficialCollar[dtourn] ~= nil) then
return fourthOfficialCollar[dtourn]
end

if (fourthOfficialCollar[0] ~= nil) then
return fourthOfficialCollar[0]
end

return colar
end



disableRealPlayerFacesSwitch = false

function disableRealPlayerFaces()
disableRealPlayerFacesSwitch = true
end



function getRandomFromID(itemarray,id)
return itemarray[(id % #itemarray)+1]
end




homeoutfieldkittypechoice = -2
awayoutfieldkittypechoice = -2
homegkkittypechoice = -2
awaygkkittypechoice = -2
refereekittypechoice = -2
homebibchoice = -2
awaybibchoice = -2

seed = 848498027

oldidx = -1
gamemodephase = -1

--Revolution Mod 16 V1.3.5
--Edited by scouser09