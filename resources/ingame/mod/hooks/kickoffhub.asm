DefineFunction2 CGFS16_EntryInit() regs=6 flags=0x129 {
  EA_PushValueOfVar 'game'
  push 'screens'
  GetMember
  push 'playNow'
  GetMember
  push 'KickOffHub'
  GetMember
  StoreRegister r3
  Pop
  EA_PushRegister r3
  EA_PushUndefined
  Equals2
  Not
  StoreRegister r5
  Pop
  EA_PushRegister r5
  Not
  If c4_keep
  EA_PushRegister r3
  push 'prototype'
  GetMember
  push 'cgfs16Keys'
  GetMember
  EA_PushUndefined
  Equals2
  Jump c3_end
  c4_keep:
  EA_PushRegister r5
  c3_end:
  Not
  If c1_else
  EA_PushRegister r3
  push 'prototype'
  GetMember
  StoreRegister r4
  Pop
  EA_PushRegister r4
  push 'cgfs16Keys'
  EA_PushRegister r4
  push 'LocalEventHandler'
  GetMember
  SetMember
  EA_PushRegister r4
  push 'cgfs16Help'
  EA_PushRegister r4
  push 'getHelpContext'
  GetMember
  SetMember
  EA_PushRegister r4
  push 'LocalEventHandler'
  DefineFunction2 (r3:keyCode, r4:controllerId) regs=5 flags=0x129 {
    EA_PushRegister r3
    EA_PushRegister r2
    push 'INPUTCODE'
    GetMember
    push 'R3'
    GetMember
    Equals2
    Not
    If c5_else
    EA_PushRegister r2
    push 'GameServices'
    GetMember
    push 'eSoundEvent'
    GetMember
    push 'PRIMARY_SELECT'
    GetMember
    push 1
    EA_PushRegister r2
    push 'playSound'
    CallMethod
    Pop
    push 'CGFS16MenuKickOff'
    EA_PushValueOfVar 'game'
    push 'uif'
    GetMember
    push 'UIFActionList'
    GetMember
    push 'ACTION_NAV'
    GetMember
    push 2
    EA_PushValueOfVar 'game'
    push 'uif'
    GetMember
    push 'UIFUtility'
    GetMember
    push 'SendAction'
    CallMethod
    Pop
    push true
    Return
    c5_else:
    EA_PushRegister r4
    EA_PushRegister r3
    push 2
    EA_PushRegister r1
    push 'cgfs16Keys'
    CallMethod
    Return
  }
  SetMember
  EA_PushRegister r4
  push 'getHelpContext'
  DefineFunction2 () regs=4 flags=0x129 {
    push 0
    EA_PushRegister r1
    push 'cgfs16Help'
    CallMethod
    StoreRegister r3
    Pop
    EA_PushRegister r3
    EA_PushUndefined
    Equals2
    Not
    Not
    If c7_else
    push 'CGFS16'
    push 'R3'
    push 2
    EA_PushValueOfVar 'ion'
    push 'manager'
    GetMember
    push 'HelpItem'
    GetMember
    push 'CreateHelpTickerItem'
    CallMethod
    push 1
    EA_PushRegister r3
    push 'push'
    CallMethod
    Pop
    c7_else:
    EA_PushRegister r3
    Return
  }
  SetMember
  c1_else:
}
push 0
push 'CGFS16_EntryInit'
CallFunction
Pop