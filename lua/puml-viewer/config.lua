local defaults = {
  plantuml_cmd = "plantuml",
  server_port = 0,
  browser_cmd = nil,
  export_format = "png",
  export_dir = nil,
}

local allowed_keys = {
  plantuml_cmd = true,
  server_port = true,
  browser_cmd = true,
  export_format = true,
  export_dir = true,
}

local function merge(user_opts)
  user_opts = user_opts or {}
  local merged = vim.deepcopy(defaults)
  for key, value in pairs(user_opts) do
    if not allowed_keys[key] then
      error("Unknown config option: " .. key)
    end
    -- plantuml_cmd accepts both string and list forms
    if key == "plantuml_cmd" and type(value) ~= "string" and type(value) ~= "table" then
      error("plantuml_cmd must be a string or a list of strings")
    end
    merged[key] = value
  end
  return merged
end

return {
  merge = merge,
}
