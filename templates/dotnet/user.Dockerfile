ARG DOTNET_SDK_VERSION=10.0.201

COPY --from=assets dotnet-sdk-${DOTNET_SDK_VERSION}-linux-x64.tar.gz ./
RUN mkdir -p $HOME/dotnet && \
    tar zxf dotnet-sdk-${DOTNET_SDK_VERSION}-linux-x64.tar.gz -C $HOME/dotnet && \
    rm dotnet-sdk-${DOTNET_SDK_VERSION}-linux-x64.tar.gz && \
    chmod +x $HOME/dotnet/dotnet
ENV PATH="${PATH}:$HOME/dotnet"

RUN mkdir -p $HOME/.aspnet/https

RUN curl -fsSL https://raw.githubusercontent.com/microsoft/artifacts-credprovider/master/helpers/installcredprovider.sh -o "$HOME/installcredprovider.sh" && \
    chmod +x "$HOME/installcredprovider.sh" && \
    bash "$HOME/installcredprovider.sh"
