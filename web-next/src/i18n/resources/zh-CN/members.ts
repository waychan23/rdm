const members = {
  page: {
    title: "成员 · {{projectKey}}",
    addMember: "添加成员",
  },
  agent: {
    auto: "自动",
    disabled: "已停用",
    inherited: "继承其 human 的项目权限",
    status: {
      enabled: "启用",
      disabled: "停用",
    },
  },
  empty: {
    header: "项目还没有成员",
    description: "点击右上角「添加成员」把组织内的用户加入项目。",
  },
  table: {
    aria: "项目成员",
    name: "名称",
    type: "类型",
    roles: "项目角色",
    active: "活跃",
    actions: "操作",
  },
  ownerBadge: "项目经理",
  member: {
    roles: "角色",
    remove: "移出",
    status: {
      enabled: "启用",
      disabled: "停用",
    },
  },
  removeDialog: {
    title: "移出项目",
    confirm: "移出",
    body: "确定把 {{name}} 移出项目？{{extra}}",
    extra: "其 {{count}} 个 agent 也会随同移出项目。",
  },
  errors: {
    addFailed: "添加失败",
    saveFailed: "保存失败",
    removeFailed: "移除失败",
  },
  notices: {
    saved: "保存成功",
  },
  addDialog: {
    title: "添加项目成员",
    userLabel: "组织用户",
    userHint: "该用户名下的 agent 会自动加入项目；agent 不需要也不能单独添加。",
    userPlaceholder: "选择组织内的 human 用户",
    roleLabel: "项目角色",
    roleHint: "项目经理只能通过「转让项目经理」变更，不能在此授予或移除。",
    rolePlaceholder: "选择项目角色",
    cancel: "取消",
    add: "添加",
  },
  editDialog: {
    title: "项目角色 · {{name}}",
    fixedRole: "固定角色",
    rolePlaceholder: "选择项目角色",
    ownerHintLocked: "项目经理角色不可在此编辑；只能通过「转让项目经理」变更。",
    ownerHintOther: "项目经理角色不在此处设置；请在项目设置页转让。",
    cancel: "取消",
    save: "保存",
  },
};

export default members;
