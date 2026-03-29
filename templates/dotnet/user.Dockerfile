ARG DOTNET_SDK_VERSION=8.0.413

RUN curl -fSL "https://builds.dotnet.microsoft.com/dotnet/Sdk/${DOTNET_SDK_VERSION}/dotnet-sdk-${DOTNET_SDK_VERSION}-linux-x64.tar.gz" -o dotnet-sdk.tar.gz && \
    mkdir -p $HOME/dotnet && \
    tar zxf dotnet-sdk.tar.gz -C $HOME/dotnet && \
    rm dotnet-sdk.tar.gz && \
    chmod +x $HOME/dotnet/dotnet
ENV PATH="${PATH}:$HOME/dotnet"

RUN mkdir -p $HOME/.aspnet/https

RUN curl -fsSL https://raw.githubusercontent.com/microsoft/artifacts-credprovider/master/helpers/installcredprovider.sh -o "$HOME/installcredprovider.sh" && \
    chmod +x "$HOME/installcredprovider.sh" && \
    bash "$HOME/installcredprovider.sh"
