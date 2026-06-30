function BallUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local ball = as:GetTable("wvBall", idx)

	db.ball[idx].model = as:GetInt(ball, "ballModel") 
	db.ball[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	db.ball[idx].stadLightID = as:GetInt(state, "wvAttribStadLightID")
	db.ball[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then
		db.ball[idx].stadiumType = 0
	else
		db.ball[idx].stadiumType = 1
	end
	
	local ballidx = idx
	if (ballidx > 1) then
	ballidx = 1
	end
	
	local wipe3d = as:GetTable("wvWipe", ballidx)
	local stadium = as:GetTable("wvStadium", ballidx)
	local climate = as:GetInt(state, "wvAttribStadClimate")
	
	db.ball[idx].ballTournID = as:GetInt(wipe3d, "leagueID")
	db.ball[idx].ballTournID = getTournamentGraphics(db.ball[idx].ballTournID)
	db.ball[idx].ballTeamID = as:GetInt(stadium, "homeKitTeamID" )
	db.ball[idx].arenatr = -1
	
	if (idx == 0) then
	db.ball[idx].arenatr = 5
	end
	
	--CLASSIC KIT + FUT
	db.ball[idx].kitYearDecade = -1
	if (idx > 0) then
	local player = as:GetTable("wvPlayer", 9)
	local kitYearOutfield = as:GetInt(player, "kitYear")
	if (kitYearOutfield > 0) then
	db.ball[idx].ballTournID = kitYearOutfield
	db.ball[idx].kitYearDecade = math.floor(kitYearOutfield/10)*10
	end
	--if (futCustom) then
	local team = as:GetInt(player, "teamid")
	if (team == 130000) then
	db.ball[idx].ballTeamID = team
	end
	--end
	local kitid = as:GetInt(player, "kit")
	if (kitid == 7000) then
	db.ball[idx].arenatr = 5
	end
	end

	
	local weather = as:GetInt(state, "wvAttribStadWeather" )
	
	db.ball[idx].ballWinter = -1
	if (climate == 1) then
	db.ball[idx].ballWinter = 1
	end
	
	db.ball[idx].ballSnow = -1
	if (weather == 2) then
	db.ball[idx].ballSnow = 2
	end
	
	db.ball[idx].ballTournGenID = -1
	if (teamTournament[db.ball[idx].ballTeamID] ~= nil) then
	db.ball[idx].ballTournGenID = teamTournament[db.ball[idx].ballTeamID]
	end
	
	local crowd = as:GetTable("wvCrowd", 1)
	db.ball[idx].crowdDistribution = as:GetInt(crowd, "crowdDistribution")
	
end

function BallAssetBind(ball)
	local gr = gRenderables
   	local lod = 0

	gr:AddCallback(ball, lod, "BallUpdate(?)")
	gr:AddAsset(ball, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(ball, lod, "ballmesh", "${GetRMBall(?,0)}data/sceneassets/ball/ball_${db.ball[?].model}.rx3;data/sceneassets/ball/ball_23.rx3")
	gr:AddAsset(ball, lod, "balltex", "${GetRMBall(?,1)}data/sceneassets/ball/ball_${db.ball[?].model}_textures.rx3;data/sceneassets/ball/ball_23_textures.rx3")
	gr:AddAsset(ball, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.ball[?].envLighting}.rx3")	
	gr:CreateMaterialFromAttribulator(ball, lod, "ballmesh", "ball", "${AttribMaterial('ball')}" )
	gr:SetTexture(ball, lod, "ballmesh", "textures", "diffuseTexture", "balltex", "ball_cm")
	gr:SetTexture(ball, lod, "ballmesh", "textures", "normalMap", "balltex", "ball_nm")
	gr:SetTexture(ball, lod, "ballmesh", "textures", "coeffMap", "balltex", "ball_coeff")
	gr:SetTexture(ball, lod, "ballmesh", "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(ball, lod, "ballmesh", "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(ball, lod, "ballmesh", "textures", "coverageMap", "covmap_${db.ball[?].stadiumID}_${db.ball[?].stadLightID}_${db.ball[?].stadiumType}")
	return ball
end


function GetRMBall(idx,isModel)
	local ballorder = ""
	local fileType = ""
	
	if (isModel == 1) then
	fileType = "_textures"
	end

	if (db.ball[idx].arenatr > -1) then
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_0_"..db.ball[idx].arenatr..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_0_"..db.ball[idx].arenatr..""..fileType..".rx3;"
	end

	if (getTournamentFinal(db.ball[idx].ballTournID,db.ball[idx].stadiumID,db.ball[idx].crowdDistribution)) then
	-- ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_"..(db.ball[idx].ballSnow+200)..""..fileType..".rx3;"
	-- ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_"..(db.ball[idx].ballWinter+200)..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_4"..fileType..".rx3;"
	end
	
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_"..db.ball[idx].ballTournID.."_"..db.ball[idx].ballSnow..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_"..db.ball[idx].ballTournID.."_"..db.ball[idx].ballWinter..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_"..db.ball[idx].ballTournID.."_0"..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_"..db.ball[idx].ballSnow..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_"..db.ball[idx].ballWinter..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournID.."_0"..fileType..".rx3;"
	
	if (db.ball[idx].arenatr == -1) then
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].kitYearDecade.."_"..db.ball[idx].ballSnow..""..fileType..".rx3;"
	--ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].kitYearDecade.."_"..db.ball[idx].ballWinter..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].kitYearDecade.."_0"..fileType..".rx3;"
	end
	
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_0_"..db.ball[idx].ballSnow..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_0_"..db.ball[idx].ballWinter..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_"..db.ball[idx].ballTeamID.."_0_0"..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournGenID.."_"..db.ball[idx].ballSnow..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournGenID.."_"..db.ball[idx].ballWinter..""..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_"..db.ball[idx].ballTournGenID.."_0"..fileType..".rx3;"
	ballorder = ballorder.."data/sceneassets/ball/specificball_0_0_0"..fileType..".rx3;"
	return ballorder
end


isWinter = false

function useWinterBalls()
--isWinter = true
end

--Revolution Mod 16 V1.0
--Edited by scouser09