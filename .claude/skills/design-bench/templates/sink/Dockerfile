# Use the same two-stage shape for every service of the prototype: the build
# toolchain never ships, and the image holds one static binary.
FROM golang:1.27 AS build
WORKDIR /src
COPY go.mod *.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /out/sink .

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/sink /sink
ENTRYPOINT ["/sink"]
