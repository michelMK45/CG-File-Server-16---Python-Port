-------------------------------------------------------------
-- Asset module
-----------------------------------------------------------------------------
gMaterialRemapTable = gSportsRNA:GetTable("MaterialRemap")
function AttribMaterial(name)
	return gSportsRNA:GetString(gMaterialRemapTable, name)
end

gLoadAsyncTable = {}

function LoadAsync(fname)
	local handle = gSportsRNA:LoadScriptAsync(fname)
    gLoadAsyncTable[fname] = handle
end

function LoadAsyncWait()
    for fname,handle in pairs(gLoadAsyncTable) do
		gSportsRNA:LoadScriptAsyncComplete(handle)
	end
	gLoadAsyncTable = {}
end

-----------------------------------------------------------------------------
-- Fire off all load requests simultaneously to get more efficient throughput
LoadAsync("data/fifarna/lua/assets/stadium.lua")
LoadAsync("data/fifarna/lua/assets/ball.lua")

local wvstate = gSportsRNA:GetTable("wvState")
LoadAsync("data/fifarna/lua/assets/player.lua")
LoadAsync("data/fifarna/lua/assets/goalnet.lua")
LoadAsync("data/fifarna/lua/assets/refereeflag.lua")
LoadAsync("data/fifarna/lua/assets/accessory.lua")
LoadAsync("data/fifarna/lua/assets/particleseffect.lua")
LoadAsync("data/fifarna/lua/assets/particles.lua")
LoadAsync("data/fifarna/lua/assets/grass.lua")
LoadAsync("data/fifarna/lua/assets/sle.lua")
LoadAsync("data/fifarna/lua/assets/crowd.lua")
LoadAsync("data/fifarna/lua/assets/indicator.lua")
LoadAsync("data/fifarna/lua/assets/poleflag.lua")
LoadAsync("data/fifarna/lua/assets/trophy.lua")
LoadAsync("data/fifarna/lua/assets/batchsle.lua")
LoadAsync("data/fifarna/lua/assets/smallobjects.lua")
LoadAsync("data/fifarna/lua/assets/wipe3d.lua")
--LoadAsync("data/fifarna/lua/assets/volumetricfx.lua")
LoadAsync("data/fifarna/lua/assets/gameplayprop.lua")
LoadAsync("data/fifarna/lua/assets/digitalboard.lua")
--LoadAsync("data/fifarna/lua/assets/envlighting.lua")
LoadAsync("data/fifarna/lua/assets/outroprop.lua")
LoadAsync("data/fifarna/lua/assets/giantflag.lua")
LoadAsync("data/fifarna/lua/assets/fancards.lua")
LoadAsync("data/fifarna/lua/assets/genericsle.lua")
LoadAsync("data/fifarna/lua/assets/cornerflags.lua")
LoadAsync("data/fifarna/lua/assets/rain.lua")
LoadAsync("data/fifarna/lua/assets/envcubemap.lua")
LoadAsync("data/fifarna/lua/assets/rm_common.lua")

-----------------------------------------------------------------------------
function InitializeDB()
	db = {
		accessory = {},
		ball = {},
		gameplayprop = {},
		digitalboard = {},
		trophy = {},
		wipeTrophy = {},
		player = {},
		stadium = {},
		genericsle = {},
		grass = {}, 
		goalnet = {},
		crowd = {},
		--crowd3d = {},
		cornerflags = {},
		poleflag = {},
		batchsle = {},
		sle = {},
		giantflag = {},
		fancards = {},
		particleseffect = {},
		smallobject = {},
		refereeflag = {},
		--volumetricFX = {},
		wipe3d = {},
		outroprop = {},
		rain = {},
		particles = {},
		poleflag = {},
		triggers = {},
		pitchspray = {},
		nballs = 2, ntrophies = 1, nplayers = 58,
		nstadiums = 2,
		nrefereeflags = 2, 
		ngenericsle = 1, ngoalnets = 4, ngrass = 2, 
		ngiantflags = 10, -- This must be <= GiantFlag::gMaxGiantFlags
		nfancards = 3, -- This must be <= FanCards::gMaxFanCards
		naccessoriesperplayer = 10, nsles = 176, nbatchsles = 1,
		nparticleseffects = 32, nsmallobjects=1, -- nvolumetricFX = 1,
		nwipe3d = 5, nwipe3dclips = 2,
		ngameplayprops = 58, ncornerflags = 2, 
		ndigitalboards = 1,
		nrain = 2,
		nparticles = 2,
		ntriggers = 2,
		npitchsprays = 2,
		ncrowdInstances = 2
	}

	local as = gAttribSys
	local idx
	for idx=0,db.nstadiums-1 do
		db.stadium[idx] = {}
	end

	for idx=0,db.nrain-1 do
		db.rain[idx] = {}
	end

	for idx=0,db.nballs-1 do
		db.ball[idx] = {}
	end

	for idx=0,db.ntrophies-1 do
		db.trophy[idx] = {}
	end

	for idx=0,db.nsmallobjects-1 do
		db.smallobject[idx] = {}
	end

	for idx=0,db.ncornerflags-1 do
		db.cornerflags[idx] = {}
	end

	for idx=0,db.nplayers-1 do
		db.player[idx] = {}

		for accidx=0,db.naccessoriesperplayer-1 do
			db.accessory[idx * db.naccessoriesperplayer + accidx] = {}
		end
	end
	
	for idx=0,db.ngenericsle-1 do
		db.genericsle[idx] = {}
	end

	for idx=0,db.ngrass-1 do
		db.grass[idx] = {}
	end

	for idx=0,db.ngoalnets-1 do
		db.goalnet[idx] = {}
	end

	for idx=0,db.ngiantflags-1 do
		db.giantflag[idx] = {}
	end
	
	for idx=0,db.nfancards-1 do
		db.fancards[idx] = {}
	end

	db.outroprop[0] = {}
	db.outroprop[1] = {}

	for idx=0,db.nbatchsles-1 do
		db.batchsle[idx] = {}
	end
	for idx=0,db.nsles-1 do
		db.sle[idx] = {}
	end

	for idx=0,db.nparticleseffects-1 do
		db.particleseffect[idx] = {}
	end

	for idx=0, db.nrefereeflags-1 do
		db.refereeflag[idx] = {}
	end

--	for idx=0,db.nvolumetricFX-1 do
--		db.volumetricFX[idx] = {}
--	end

	for idx=0,db.nwipe3d-1 do
		db.wipe3d[idx] = {}
	end

	for idx=0,db.ngameplayprops-1 do
		db.gameplayprop[idx] = {}
	end

	for idx=0,db.ndigitalboards-1 do
		db.digitalboard[idx] = {}
	end

	for idx=0,db.nparticles-1 do
		db.particles[idx] = {}
	end

	for idx=0,db.ntriggers-1 do
		db.triggers[idx] = {}
	end


	for idx=0,db.npitchsprays-1 do
		db.pitchspray[idx] = {}
	end

	for idx=0,db.ncrowdInstances-1 do
		db.crowd[idx] = {}
	end

end

-----------------------------------------------------------------------------
function InitializeRenderables()
	gRenderObj = {
		batchSle = nil,
		sles = {},
		ball = {},
		trophy = {},
		wipeTrophy = {},
		players = {},
		stadium = {},
		refereeflag = {},
		genericsle = {},
		goalnet = {},
		particlesEffect = {},
		frameGrab = {},
		batchPlayer = nil,
		flatShadow = nil,
		lightmapgen=nil,
		lightprobesgen=nil,
		depthBufferPrePass = nil,
		crowd3d = {},
		mipmapsgen = nil,
		batchparticle = nil,
		poleflag = nil,
		gameplayprop = {},
		digitalboard = {},
		giantflag = {},
		fancards = {},
		postfx = nil,
		postfx_ssao = nil,
		indicator = nil,
		pitchlines = nil,
		selfshadow = nil,
		motionblur = nil,
		ferenderable = nil,
		onscreenimage = nil,
		smallobjects = {},
		flatrender = nil,
--		volumetricFX = {},
		wipe3d = {},
		wipe3dclip = {},
		--envlighting = nil,
		outroprop = {},
		grass = {},
		cornerflags = {},
		rain = {},
		particles = {},
		triggers = {},
		pitchspray = {},
        flushdispatcher = {},
        envcubemap = {},
	} 

	local gr = gRenderables

	gRenderObj.lightmapgen = gr:Create("lightmapgen", 0)
	gRenderObj.lightprobesgen = gr:Create("lightprobesgen", 0)
    gRenderObj.envcubemap = gr:Create("envcubemap", 0)

	local idx
	for idx=0,db.nstadiums-1 do
		gRenderObj.stadium[idx] = gr:Create("stadium", idx)
	end

	for idx=0,db.nrain-1 do
		gRenderObj.rain[idx] = gr:Create("rain", idx)
	end

	for idx=0,db.nparticles-1 do
		gRenderObj.particles[idx] = gr:Create("fifaparticles", idx)
	end

	for idx=0,db.nballs-1 do
		gRenderObj.ball[idx] = gr:Create("ball", idx)
	end

	for idx=0,db.ntrophies-1 do
		gRenderObj.trophy[idx] = gr:Create("trophy", idx)
	end

	gRenderObj.wipeTrophy = gr:Create("trophy", db.ntrophies);
	
	for idx=0,db.ngenericsle-1 do
		gRenderObj.genericsle[idx] = gr:Create("genericsle", idx)
	end

	for idx=0,db.ngoalnets-1 do
		gRenderObj.goalnet[idx] = gr:Create("goalnet", idx)
	end

	for idx=0,db.ngiantflags-1 do
		gRenderObj.giantflag[idx] = gr:Create("giantflag", idx)
	end
	
	for idx=0,db.nfancards-1 do
		gRenderObj.fancards[idx] = gr:Create("fancards", idx)
	end

	for idx=0,db.nrefereeflags-1 do
		gRenderObj.refereeflag[idx] = gr:Create("refereeflag", idx)
	end

	for idx=0,db.ngrass-1 do
		gRenderObj.grass[idx] = gr:Create("grass", idx)
	end

	for idx=0,db.ncornerflags-1 do
		gRenderObj.cornerflags[idx] = gr:Create("cornerflags", idx)
	end

	for idx=0,db.ntriggers-1 do
		gRenderObj.triggers[idx] = gr:Create("triggers", idx)
	end

	for idx=0,db.npitchsprays-1 do
		gRenderObj.pitchspray[idx] = gr:Create("pitchspray", idx)
	end
		
	gRenderObj.outroprop[0] = gr:Create("outroprop", 0) -- home
	gRenderObj.outroprop[1] = gr:Create("outroprop", 1) -- away

	gRenderObj.batchSle = gr:Create("batchsle", 0)
	gRenderObj.batchPlayer = gr:Create("batchplayer", 0)
	gRenderObj.flatShadow = gr:Create("flatshadow", 0)
	--gRenderObj.depthBufferPrePass = gr:Create("depthbufferprepass", 0)
	--gRenderObj.postfx_ssao = gr:Create("pfx_ssao", 0)

	-- create crowd object and add stadium 1 as subobject for updates
	--gRenderObj.crowd = gr:Create("crowd", 0)
	--gr:AddSubObject(gRenderObj.crowd, gRenderObj.stadium[1])
	
	for idx=0,db.ncrowdInstances-1 do
		gRenderObj.crowd3d[idx] = gr:Create("crowd3d", idx)
	end

	gr:AddSubObject(gRenderObj.crowd3d[0], gRenderObj.stadium[0])
	gr:AddSubObject(gRenderObj.crowd3d[1], gRenderObj.stadium[1])

	gRenderObj.mipmapsgen = gr:Create("mipmapsgen", 0)

	gRenderObj.frameGrab[0] = gr:Create("framegrab", 0)
	gRenderObj.frameGrab[1] = gr:Create("framegrab", 1)

	gRenderObj.msaa = gr:Create("msaa", 1)
	gRenderObj.postfx = gr:Create("postfx", 0)
	gRenderObj.batchparticle = gr:Create("batchparticle", 0)
	gRenderObj.poleflag = gr:Create("poleflag", 0)
	gRenderObj.indicator = gr:Create("indicator", 0)
	gRenderObj.pitchlines = gr:Create("pitchlines", 0)
--	gRenderObj.selfshadow = gr:Create("selfshadow", 0)
	gRenderObj.selfshadow = gr:Create("selfshadowpo", 0)
	gRenderObj.motionblur = gr:Create("motionblur", 0)
	gRenderObj.ferenderable = gr:Create("ferenderable", 0)
	--gRenderObj.onscreenimage = gr:Create("onscreenimage", 0)
    gRenderObj.jumbotron = gr:Create("jumbotron", 0)

	gRenderObj.smallobjects[0] = gr:Create("smallobject", 0)
    gRenderObj.flushdispatcher = gr:Create("flushdispatcher", 0)

	-- Create the Gameplay props using the base renderable implementation
	for idx=0,db.ngameplayprops-1 do
		gRenderObj.gameplayprop[idx] = gr:Create("gameplayprop", idx)
	end

	-- Create digital board
	for idx=0,db.ndigitalboards-1 do
		gRenderObj.digitalboard[idx] = gr:Create("digitalboard", idx)
	end
    gRenderObj.flatrender = gr:Create("flatrender", 0)
    gr:AddSubObject(gRenderObj.flatrender, gRenderObj.batchPlayer)

	-- Create players, and add them to the batchplayer object
	for idx=0,db.nplayers-1 do
		player = gr:Create("player", idx)
		gRenderObj.players[ idx ] = player


		for accidx=0,db.naccessoriesperplayer-1 do
			accessory = gr:Create("accessory", idx * db.naccessoriesperplayer + accidx)
			gr:AddSubObject(player, accessory);
		end

		gr:AddSubObject(gRenderObj.batchPlayer, player)
	end
	
	-- Set the maximum instances of SLE for each type
	SetSleSettings()

	-- Create sles, and add them to the batchSle object
	CreateSleVariations(gr, gRenderObj.batchSle, gRenderObj.sles)
	db.nsles = table.getn(gRenderObj.sles)

	-- Add all objects that are required to the depthbufferPrePassObject
	local dbpp = gRenderObj.depthBufferPrePass
	if (dbpp ~= nil) then
		for idx=0,db.nstadiums-1 do
			gr:AddSubObject(dbpp, gRenderObj.stadium[idx])
		end
		for idx=0,db.nballs-1 do
			gr:AddSubObject(dbpp, gRenderObj.ball[idx])
		end
		for idx=0,db.ntrophies-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.trophy[idx])
		end
		for idx=0,db.nrefereeflags-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.refereeflag[idx])
		end
		for idx=0,db.ngoalnets-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.goalnet[idx])
		end
		for idx=0,db.ngiantflags-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.giantflag[idx])
		end
	--	gr:AddSubObject(dbpp, gRenderObj.crowd)
		gr:AddSubObject(dbpp, gRenderObj.batchPlayer)
	--	gr:AddSubObject(dbpp, gRenderObj.batchSle)

		for idx=0,db.ngameplayprops-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.gameplayprop[idx], 3) -- Tell dbpp to use pass 3 (dbpp pass) instead of dbpp interface
		end

		for idx=0,db.ndigitalboards-1 do
	--		gr:AddSubObject(dbpp, gRenderObj.digitalboard[idx], 3) -- Tell dbpp to use pass 3 (dbpp pass) instead of dbpp interface
		end
	end

	-- Add ball, batchsle and batchplayer object to the flat shadow renderer
	gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.batchSle)
	gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.batchPlayer)
	gr:AddSubObject(gRenderObj.selfshadow, gRenderObj.batchPlayer)
	gr:AddSubObject(gRenderObj.motionblur, gRenderObj.batchPlayer)
	
	for idx=0,db.ngenericsle-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.genericsle[idx])
	end

	for idx=0,db.nballs-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.ball[idx])
		gr:AddSubObject(gRenderObj.selfshadow, gRenderObj.ball[idx])
		gr:AddSubObject(gRenderObj.motionblur, gRenderObj.ball[idx])
	end

	for idx=0,db.ntrophies-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.trophy[idx])
		gr:AddSubObject(gRenderObj.selfshadow, gRenderObj.trophy[idx])
		--gr:AddSubObject(gRenderObj.motionblur, gRenderObj.trophy[idx])
	end

	for idx=0,db.ngoalnets-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.goalnet[idx])
	end

	for idx=0,db.ngameplayprops-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.gameplayprop[idx], 2) -- Tell flatshadow to use pass 2 (flatshadow pass) instead of flatshadow interface
		gr:AddSubObject(gRenderObj.selfshadow, gRenderObj.gameplayprop[idx], 4) -- Tell selfshadow to use pass 4 (selfshadow pass) instead of selfshadow interface
	end

	for idx=0,db.ndigitalboards-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.digitalboard[idx], 2) -- Tell flatshadow to use pass 2 (flatshadow pass) instead of flatshadow interface
		gr:AddSubObject(gRenderObj.selfshadow, gRenderObj.digitalboard[idx], 4) -- Tell selfshadow to use pass 4 (selfshadow pass) instead of selfshadow interface
	end

	gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.outroprop[0])
	gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.outroprop[1])

--	for idx=0,db.nvolumetricFX-1 do
--		gRenderObj.volumetricFX[idx] = gr:Create("volumetricfx", idx)
--	end

	-- Create wipe elements before creating clips
	for idx=0,db.nwipe3d-1 do
		gRenderObj.wipe3d[idx] = gr:Create("wipe3d", idx)
	end
	-- create wipe movies
	for idx=0,db.nwipe3dclips-1 do
		gRenderObj.wipe3dclip[idx] = gr:Create("wipe3dclip", idx)
	end
	-- build replay wipe
	gr:AddSubObject(gRenderObj.wipe3dclip[0], gRenderObj.wipe3d[0])
	-- build intro wipe
	for idx=1,db.nwipe3d-1 do
		gr:AddSubObject(gRenderObj.wipe3dclip[1], gRenderObj.wipe3d[idx])
	end

	-- Create particles effect, and add them to the particles object
	for idx=0,db.nparticleseffects-1 do
		particlesEffect = gr:Create("particleseffect", idx)
		gRenderObj.particlesEffect[ idx ] = particlesEffect
	end

	gr:AddSubObject(gRenderObj.batchparticle, gRenderObj.batchPlayer, 6); -- after postfx depth pass (draw hair strands to downsampled depth)

	for idx=0,db.ncornerflags-1 do
		gr:AddSubObject(gRenderObj.flatShadow, gRenderObj.cornerflags[idx])
	end

	--gRenderObj.envlighting = gr:Create("envlighting", 0)

	-----------------------------------------------------------------------------
	-- Init post fx passes with renderables
	CreatePostFXRenderables( gRenderObj, gr )
end

-----------------------------------------------------------------------------
InitializeDB()
LoadAsyncWait() -- ensure all files are loaded
LoadAsync("data/fifarna/lua/assignments/general.lua")
LoadAsyncWait()
InitializeRenderables()
collectgarbage('collect')

--Revolution Mod 16 V1.0
--Edited by scouser09