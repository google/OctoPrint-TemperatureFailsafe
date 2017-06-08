$(function() {
    function TemperaturefailsafeViewModel(parameters) {
        var self = this;
        var msgTitle = "TemperatureFailsafe";
        var msgType = "error";
        var autoClose = false;

        self.settingsViewModel = parameters[0];

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "TemperatureFailsafe") {
                return;
            }

            if (data.type == "popup") {
                new PNotify({
                    text: data.msg,
                    title: msgTitle,
                    type: msgType,
                    hide: autoClose
                });
            }
        }
    }

    ADDITIONAL_VIEWMODELS.push([
        TemperaturefailsafeViewModel,

        // This is a list of dependencies to inject into the plugin, the order which you request
        // here is the order in which the dependencies will be injected into your view model upon
        // instantiation via the parameters argument
        [],

        // Finally, this is the list of selectors for all elements we want this view model to be bound to.
        []
    ]);
});
